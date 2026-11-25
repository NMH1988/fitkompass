"""A gymer's Art. 9 consents to send their data to a model, one purpose each (T11.5, D25).

Art. 9 consent must be specific, so each purpose of `docs/PRD.md`'s consents (a)-(e) is given and
withdrawn on its own, apart from the sharing scopes (`users`, the `consents` table): another
purpose's consent never counts. A row keeps the version of the text the gymer agreed to; a flow
checks `is_given()` with the version of the text it shows now, so a changed text counts as no
consent until the gymer gives it again. The purposes given to one coach (`coach_thread`, (b), and
`client_notes`, (e)) name the relationship they belong to, and count only while it is active: one
open consent per purpose, and per relationship for those two.

Only a gymer gives a consent, only their own, and for (b) and (e) only for their own active
relationship; every other case is the same `NotFound` and writes nothing. A consent is withdrawn by
setting its `withdrawn_at` (the one change the table's trigger allows, as `consents.revoked_at` is
set); giving it again adds a row, so the rows are its history, which the gymer's export holds.
`is_given()` answers False for anything it cannot read as a consent, so a flow fails closed.
"""

import sqlite3
from typing import Literal, get_args

from src.store import values
from src.store.access import NotFound, role_of
from src.store.db import transaction

Purpose = Literal["message_drafts", "coach_thread", "media", "dish_suggestions", "client_notes"]
PURPOSES: tuple[str, ...] = get_args(Purpose)
# The purposes given to one coach, which keep the relationship they belong to (PRD (b) and (e)).
PER_RELATIONSHIP: tuple[str, ...] = ("coach_thread", "client_notes")

_RELATIONSHIP = "SELECT client_id, ended_at FROM coach_clients WHERE id = ?"
_OPEN = """
SELECT id, user_id, purpose, relationship_id, text_version, given_at, withdrawn_at
FROM ai_consents
WHERE user_id = ? AND purpose = ? AND ifnull(relationship_id, 0) = ? AND withdrawn_at IS NULL
"""
_GIVE = """
INSERT INTO ai_consents (user_id, purpose, relationship_id, text_version, given_at)
VALUES (?, ?, ?, ?, ?)
"""
_WITHDRAW = "UPDATE ai_consents SET withdrawn_at = ? WHERE id = ?"


def _version(value: object) -> str:
    """Return the value if it is a consent text's version (12 hex characters, as a prompt's)."""
    return values.prompt_version(value, "text_version")


def _target(
    conn: sqlite3.Connection, user_id: object, purpose: object, relationship_id: object
) -> tuple[str, str, int]:
    """Check who consents to what, inside the caller's transaction; return the open row's key."""
    # The same NotFound for a malformed or foreign value, a coach, an unknown purpose, a
    # relationship where the purpose takes none (or none where it needs one), and an ended or a
    # foreign one.
    try:
        user_id = values.user_id(user_id)
    except values.StoreValueError:
        raise NotFound from None
    if purpose not in PURPOSES or role_of(conn, user_id) != "gymer":
        raise NotFound
    if purpose not in PER_RELATIONSHIP:
        if relationship_id is not None:
            raise NotFound
        return user_id, purpose, 0
    if not values.is_row_id(relationship_id):
        raise NotFound
    relationship = conn.execute(_RELATIONSHIP, (relationship_id,)).fetchone()
    if relationship is None or relationship["client_id"] != user_id:
        raise NotFound
    if relationship["ended_at"] is not None:
        raise NotFound  # read as a value: a consent to an ended relationship's coach is none
    return user_id, purpose, relationship_id


def give(
    conn: sqlite3.Connection,
    user_id: str,
    purpose: Purpose,
    text_version: str,
    relationship_id: int | None = None,
) -> int:
    """Record the gymer's consent to a text's version; return its row ID, else NotFound."""
    # Giving the same version again keeps the open row; another version withdraws it first, so the
    # history shows which text was agreed to when.
    version = _version(text_version)
    with transaction(conn):
        user_id, purpose, key = _target(conn, user_id, purpose, relationship_id)
        current = conn.execute(_OPEN, (user_id, purpose, key)).fetchone()
        now = values.utc_text()
        if current is not None:
            if current["text_version"] == version:
                return current["id"]
            conn.execute(_WITHDRAW, (now, current["id"]))
        row = (user_id, purpose, key or None, version, now)
        return conn.execute(_GIVE, row).lastrowid


def withdraw(
    conn: sqlite3.Connection,
    user_id: str,
    purpose: Purpose,
    relationship_id: int | None = None,
) -> bool:
    """Withdraw the gymer's open consent; return whether one was open, NotFound for a bad target."""
    # A (b) or (e) of an ended relationship already counts as none, so it is not withdrawn here.
    with transaction(conn):
        user_id, purpose, key = _target(conn, user_id, purpose, relationship_id)
        current = conn.execute(_OPEN, (user_id, purpose, key)).fetchone()
        if current is None:
            return False
        conn.execute(_WITHDRAW, (values.utc_text(), current["id"]))
        return True


def current(
    conn: sqlite3.Connection,
    user_id: str,
    purpose: Purpose,
    relationship_id: int | None = None,
) -> dict | None:
    """Return the gymer's open consent for a purpose (any version), or None; NotFound if bad."""
    with transaction(conn):
        user_id, purpose, key = _target(conn, user_id, purpose, relationship_id)
        row = conn.execute(_OPEN, (user_id, purpose, key)).fetchone()
        return None if row is None else dict(row)


def is_given(
    conn: sqlite3.Connection,
    user_id: object,
    purpose: object,
    text_version: object,
    relationship_id: object = None,
) -> bool:
    """Return True only if the gymer's open consent to this exact text version holds now."""
    # Checked again right before each model call (PRD "Consents"): anything it cannot read as a
    # consent, a changed text's version, a withdrawn one or an ended relationship is False.
    try:
        version = _version(text_version)
        with transaction(conn):
            user_id, purpose, key = _target(conn, user_id, purpose, relationship_id)
            row = conn.execute(_OPEN, (user_id, purpose, key)).fetchone()
    except NotFound, values.StoreValueError:
        return False
    return row is not None and row["text_version"] == version
