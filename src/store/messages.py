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
"""

import sqlite3

from src import config
from src.store import values
from src.store.access import NotFound, role_of
from src.store.db import transaction

_RELATIONSHIP = "SELECT coach_id, client_id, ended_at FROM coach_clients WHERE id = ?"
_INSERT = """
INSERT INTO messages (relationship_id, sender_id, text, created_at) VALUES (?, ?, ?, ?)
"""
# A thread's messages after a given ID, oldest first: the whole thread from 0, and only the ones a
# page has not shown yet after a reconnect (T11.4a).
_THREAD = """
SELECT id, relationship_id, sender_id, text, created_at FROM messages
WHERE relationship_id = ? AND id > ? ORDER BY id
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
    conn: sqlite3.Connection, reader_id: str, relationship_id: int, *, after_id: int = 0
) -> list[dict]:
    """Return a thread's messages after `after_id`, oldest first, to one of its two sides."""
    after_id = values.whole_number(after_id, "after_id")
    with transaction(conn):
        _thread_side(conn, reader_id, relationship_id)
        return [dict(row) for row in conn.execute(_THREAD, (relationship_id, after_id))]
