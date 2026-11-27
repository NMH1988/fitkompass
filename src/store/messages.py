"""Messages between a coach and a client (T11.3, PRD feature 30): one thread per relationship.

A thread is a coach-client relationship (its `coach_clients` row). Only its two sides read it, and
they read it also after the relationship ended; only they write to it, and only while it is active.
Every other case (a missing or malformed ID, a stranger, a side of another relationship, a write
after the end) gets the same `NotFound`, and nothing is written. The check is the relationship
itself, as `users.display_name_of()`'s is, not a sharing scope: a message is correspondence between
the two, not data the gymer shares. A relationship's end is read as a value (`ended_at`), never as a
sharing filter, which only the `open_shares` view writes.

A thread read is not audited: both readers are parties to the conversation, and an audit row for
every message pushed to an open page would flood the log (a recorded exception to "every coach read
is audited", `.claude/rules/security-privacy.md`). A message is never changed in place and is never
sent to a model here; its text is never logged, and an error names the field, never the value.

The coach's AI reads a thread for the coach (T11.6a, D30) only through `thread_for_coach_ai()`: the
coach's newest relationship with the client must be active and the client's consent (b) must have
that use switched on under its current text, both checked in the same transaction as the read, else
the same `NotFound`; `is_open_for_coach_ai()` makes the same check without reading a message, right
before each model call. Like a person's read, the AI's read writes no audit row (T11.6a); what
the model may then receive is the caller's (`src/tools/client_thread.py`).
"""

import sqlite3
from datetime import datetime

from src import config
from src.store import ai_consents, values
from src.store.access import NotFound, role_of
from src.store.db import transaction

_RELATIONSHIP = "SELECT coach_id, client_id, ended_at FROM coach_clients WHERE id = ?"
_INSERT = """
INSERT INTO messages (relationship_id, sender_id, text, created_at) VALUES (?, ?, ?, ?)
"""
# A thread's messages after a given ID, oldest first: the whole thread from 0, and only the ones a
# page has not shown yet after a reconnect (T11.4a), at most LIMIT of them (-1: no limit).
_THREAD = """
SELECT id, relationship_id, sender_id, text, created_at FROM messages
WHERE relationship_id = ? AND id > ? ORDER BY id LIMIT ?
"""
# The coach's newest relationship with a client: the one an AI read may use, if it is still active.
_NEWEST_PAIR = """
SELECT id, ended_at FROM coach_clients WHERE coach_id = ? AND client_id = ? ORDER BY id DESC LIMIT 1
"""
# A thread's messages sent in [start, end), the newest LIMIT of them, newest first.
_WINDOW = """
SELECT id, sender_id, text, created_at FROM messages
WHERE relationship_id = ? AND created_at >= ? AND created_at < ? ORDER BY id DESC LIMIT ?
"""


def _thread_side(conn: sqlite3.Connection, user_id: object, relationship_id: object) -> sqlite3.Row:
    """Return the relationship when the user is one of its two sides; else NotFound."""
    # Runs inside the caller's transaction. A value that cannot be an ID is the same NotFound as a
    # missing row, so an answer never tells a malformed request from a foreign thread.
    try:
        values.user_id(user_id)
    except values.StoreValueError:
        raise NotFound from None
    if not values.is_row_id(relationship_id) or role_of(conn, user_id) is None:
        raise NotFound
    relationship = conn.execute(_RELATIONSHIP, (relationship_id,)).fetchone()
    if relationship is None or user_id not in (relationship["coach_id"], relationship["client_id"]):
        raise NotFound
    return relationship


def send_message(conn: sqlite3.Connection, sender_id: str, relationship_id: int, text: str) -> int:
    """Store a message from a side of an active relationship; return its ID, else NotFound."""
    # The text is checked before the transaction, so a bad one writes nothing (its error names the
    # field only). The side check, the end check and the insert are one transaction.
    checked = values.text(text, "text", config.MESSAGE_MAX_CHARS)
    with transaction(conn):
        relationship = _thread_side(conn, sender_id, relationship_id)
        if relationship["ended_at"] is not None:
            raise NotFound  # read-only after the end: the same answer as a foreign thread
        cursor = conn.execute(_INSERT, (relationship_id, sender_id, checked, values.utc_text()))
        return cursor.lastrowid


def list_messages(
    conn: sqlite3.Connection,
    reader_id: str,
    relationship_id: int,
    *,
    after_id: int = 0,
    limit: int | None = None,
) -> list[dict]:
    """Return a thread's messages after `after_id`, oldest first, at most `limit`, to a side."""
    after_id = values.whole_number(after_id, "after_id")
    # The chat socket's catch-up reads a bounded batch (config.CHAT_CATCH_UP_LIMIT, T11.4a).
    bound = -1 if limit is None else values.whole_number(limit, "limit", minimum=1)
    with transaction(conn):
        _thread_side(conn, reader_id, relationship_id)
        return [dict(row) for row in conn.execute(_THREAD, (relationship_id, after_id, bound))]


def _ai_thread(
    conn: sqlite3.Connection, coach_id: object, client_id: object, use: object, version: object
) -> int:
    """Return the relationship an AI read for the coach may use, inside the caller's transaction."""
    # NotFound for a malformed or unknown user, a coach who is not the client's, an ended
    # relationship (read as a value), or no consent (b) with this use under this text's version.
    try:
        values.user_id(coach_id)
        values.user_id(client_id)
    except values.StoreValueError:
        raise NotFound from None
    if role_of(conn, coach_id) != "coach" or role_of(conn, client_id) != "gymer":
        raise NotFound
    relationship = conn.execute(_NEWEST_PAIR, (coach_id, client_id)).fetchone()
    if relationship is None or relationship["ended_at"] is not None:
        raise NotFound
    row = ai_consents._open_row(conn, client_id, ai_consents.WITH_USES, relationship["id"], use)
    if row is None or row["text_version"] != version:
        raise NotFound
    return relationship["id"]


def is_open_for_coach_ai(
    conn: sqlite3.Connection, coach_id: object, client_id: object, use: object, version: object
) -> bool:
    """Return whether the coach's AI may read the thread now: active, and the use switched on."""
    try:
        with transaction(conn):
            _ai_thread(conn, coach_id, client_id, use, version)
    except NotFound, values.StoreValueError:
        return False
    return True


def thread_for_coach_ai(
    conn: sqlite3.Connection,
    coach_id: str,
    client_id: str,
    use: str,
    version: str,
    *,
    start: datetime,
    end: datetime,
    limit: int,
) -> list[dict]:
    """Return the newest `limit` messages sent in [start, end), oldest first, for the coach's AI."""
    # Only with the client's consent (b) for this use and an active relationship, checked in the
    # read's own transaction; else NotFound. Both sides' messages, as the consent's text says.
    bound = values.whole_number(limit, "limit", minimum=1)
    first, last = values.utc_text(start), values.utc_text(end)
    with transaction(conn):
        relationship_id = _ai_thread(conn, coach_id, client_id, use, version)
        rows = conn.execute(_WINDOW, (relationship_id, first, last, bound)).fetchall()
    return [dict(row) for row in reversed(rows)]
