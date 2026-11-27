"""Which of a gymer's messages the drafting workflow has finished, and its one-step write (T11.5).

The workflow (`src/agent/drafts.py`, D26) drafts log entries from the gymer's own messages. Once it
has finished with a message (its cards decided in one step, no card found in it, or the message
refused by the guard), the message gets a row in `message_drafts`, unique per message, so it never
reaches a model again. `save_step()` writes the step's approved entries and that row in one
transaction (`BEGIN IMMEDIATE`, so two steps wait for each other), after checking inside it that
the message has no row yet: the same message decided in two tabs is logged once, and a failed write
leaves neither. `save_entries()` writes the approved entries drafted from a photo or a voice note
(T11.10), which refer to nothing, as the file is never stored. `mark_finished()` writes the row
alone for a message with no card or a refused one; a second such write is a no-op. The row refers
to the message and goes with it (either side's delete); no logged entry refers to a message, so
neither side's delete is blocked.

Only the gymer reads their own messages here and writes their own entries; every other case is the
same `NotFound`, and nothing is written. A relationship's end is read as a value (`ended_at`).
The entries' values are checked by `records`' own row checks; the day window and the food log's
gram range are the diary's (`src/drafting.py` checks them first).
"""

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from src.store import records, values
from src.store.access import NotFound, role_of
from src.store.db import transaction

_RELATIONSHIP = "SELECT client_id, ended_at FROM coach_clients WHERE id = ?"
_SENDER = "SELECT sender_id, created_at FROM messages WHERE id = ?"
# The message as the run read it: the same thread, sender and time, and no drafted mark yet.
_STILL_UNDRAFTED = """
SELECT 1 FROM messages AS message
WHERE message.id = ? AND message.relationship_id = ? AND message.sender_id = ?
    AND message.created_at = ?
    AND NOT EXISTS (SELECT 1 FROM message_drafts AS drafted WHERE drafted.message_id = message.id)
"""
_DRAFTED = "SELECT 1 FROM message_drafts WHERE message_id = ?"
_MARK = "INSERT INTO message_drafts (message_id) VALUES (?) ON CONFLICT (message_id) DO NOTHING"
# The gymer's own messages in one thread, sent from a given time, that have no drafted row yet,
# oldest first, at most LIMIT of them.
_UNDRAFTED = """
SELECT message.id, message.text, message.created_at FROM messages AS message
WHERE message.relationship_id = ? AND message.sender_id = ? AND message.created_at >= ?
    AND NOT EXISTS (SELECT 1 FROM message_drafts AS drafted WHERE drafted.message_id = message.id)
ORDER BY message.id LIMIT ?
"""


@dataclass(frozen=True)
class DraftedFood:
    """An approved food: its day, meal slot, USDA food and the nutrients of its grams (code's)."""

    consumed_on: date
    meal: records.Meal
    fdc_id: int
    food_name: str
    grams: float
    kcal: float
    protein_g: float
    carbohydrate_g: float
    fat_g: float
    fiber_g: float | None


@dataclass(frozen=True)
class DraftedWeight:
    """An approved weight in kg on a day."""

    weight_kg: float
    measured_on: date


@dataclass(frozen=True)
class DraftedWorkout:
    """An approved workout: its day and its sets (exercises of the fixed list)."""

    performed_on: date
    sets: tuple[records.ExerciseSet, ...]


def _own_message(
    conn: sqlite3.Connection, user_id: object, message_id: object, created_at: object = None
) -> str:
    """Return the gymer's checked ID when the message is theirs, inside the caller's transaction."""
    # With created_at, the message must also be the one sent then: an ID freed by a delete and
    # taken by a later row is not the message whose cards the gymer decided.
    try:
        user_id = values.user_id(user_id)
    except values.StoreValueError:
        raise NotFound from None
    if not values.is_row_id(message_id) or role_of(conn, user_id) != "gymer":
        raise NotFound
    row = conn.execute(_SENDER, (message_id,)).fetchone()
    if row is None or row["sender_id"] != user_id:
        raise NotFound
    if created_at is not None and row["created_at"] != created_at:
        raise NotFound
    return user_id


def undrafted_messages(
    conn: sqlite3.Connection,
    user_id: str,
    relationship_id: int,
    *,
    since: datetime,
    limit: int,
) -> list[dict]:
    """Return the gymer's own undrafted messages of their active thread, oldest first."""
    # Only the client's own messages, never the coach's (T11.5), and only while the relationship is
    # active; else NotFound.
    bound = values.whole_number(limit, "limit", minimum=1)
    start = values.utc_text(since)
    try:
        user_id = values.user_id(user_id)
    except values.StoreValueError:
        raise NotFound from None
    with transaction(conn):
        if not values.is_row_id(relationship_id) or role_of(conn, user_id) != "gymer":
            raise NotFound
        relationship = conn.execute(_RELATIONSHIP, (relationship_id,)).fetchone()
        if relationship is None or relationship["client_id"] != user_id:
            raise NotFound
        if relationship["ended_at"] is not None:
            raise NotFound
        rows = conn.execute(_UNDRAFTED, (relationship_id, user_id, start, bound)).fetchall()
    return [dict(row) for row in rows]


def is_open_thread(conn: sqlite3.Connection, user_id: object, relationship_id: object) -> bool:
    """Return whether the relationship is the gymer's own and still active; False for any other."""
    # Checked again right before each model call, so a run never sends a message of a thread that
    # ended while it waited (the end read as a value).
    try:
        user_id = values.user_id(user_id)
    except values.StoreValueError:
        return False
    if not values.is_row_id(relationship_id):
        return False
    with transaction(conn):
        relationship = conn.execute(_RELATIONSHIP, (relationship_id,)).fetchone()
    return (
        relationship is not None
        and relationship["client_id"] == user_id
        and relationship["ended_at"] is None
    )


def is_still_undrafted(
    conn: sqlite3.Connection,
    user_id: object,
    relationship_id: object,
    message_id: object,
    created_at: object,
) -> bool:
    """Return whether the gymer's message is still there as the run read it, with no mark yet."""
    # Checked right before its model call: a message deleted meanwhile (with either side's data,
    # its ID then free for a later row) or finished in another tab is not sent. The time tells a
    # reused ID from the message the run read.
    try:
        user_id = values.user_id(user_id)
    except values.StoreValueError:
        return False
    if not (values.is_row_id(relationship_id) and values.is_row_id(message_id)):
        return False
    if not isinstance(created_at, str):
        return False
    with transaction(conn):
        row = conn.execute(
            _STILL_UNDRAFTED, (message_id, relationship_id, user_id, created_at)
        ).fetchone()
    return row is not None


def mark_finished(
    conn: sqlite3.Connection, user_id: str, message_id: int, created_at: str | None = None
) -> bool:
    """Mark the gymer's own message as finished with; return False if it already was."""
    # For a message with no card or one the guard refused: nothing is logged, so a second write
    # (another tab) is a no-op here, never an IntegrityError reaching the page. With created_at,
    # a later row that took a deleted message's ID is not marked (NotFound).
    with transaction(conn):
        _own_message(conn, user_id, message_id, created_at)
        return conn.execute(_MARK, (message_id,)).rowcount == 1


def _rows(
    user_id: str,
    foods: Sequence[DraftedFood],
    weights: Sequence[DraftedWeight],
    workouts: Sequence[DraftedWorkout],
) -> tuple[list[tuple], list[tuple], list[tuple]]:
    """Return the entries' checked rows, so a bad value raises before any transaction starts."""
    food_rows = [
        records._meal_row(
            user_id,
            food.consumed_on,
            food.meal,
            food.fdc_id,
            food.food_name,
            food.grams,
            food.kcal,
            food.protein_g,
            food.carbohydrate_g,
            food.fat_g,
            food.fiber_g,
        )
        for food in foods
    ]
    weight_rows = [records._weight_row(user_id, w.weight_kg, w.measured_on) for w in weights]
    workout_rows = [
        (records._workout_day(user_id, workout.performed_on), records._checked_sets(workout.sets))
        for workout in workouts
    ]
    return food_rows, weight_rows, workout_rows


def _write_rows(
    conn: sqlite3.Connection, rows: tuple[list[tuple], list[tuple], list[tuple]]
) -> None:
    """Write checked rows inside the caller's transaction."""
    food_rows, weight_rows, workout_rows = rows
    for row in food_rows:
        records._write_meal(conn, row)
    for row in weight_rows:
        records._write_weight(conn, row)
    for session, checked in workout_rows:
        records._write_session(conn, session, checked)


def save_step(
    conn: sqlite3.Connection,
    user_id: str,
    message_id: int,
    *,
    foods: Sequence[DraftedFood] = (),
    weights: Sequence[DraftedWeight] = (),
    workouts: Sequence[DraftedWorkout] = (),
    created_at: str | None = None,
) -> bool:
    """Log a message's approved entries and mark it, in one transaction; False if already marked."""
    # Every row is checked before the transaction, so a bad value writes nothing. Inside it: the
    # message is the gymer's own and has no drafted row yet; if it has one, nothing is written.
    rows = _rows(user_id, foods, weights, workouts)
    with transaction(conn):
        _own_message(conn, user_id, message_id, created_at)
        if conn.execute(_DRAFTED, (message_id,)).fetchone() is not None:
            return False
        _write_rows(conn, rows)
        conn.execute(_MARK, (message_id,))
        return True


def save_entries(
    conn: sqlite3.Connection,
    user_id: object,
    *,
    foods: Sequence[DraftedFood] = (),
    weights: Sequence[DraftedWeight] = (),
    workouts: Sequence[DraftedWorkout] = (),
) -> int:
    """Log a gymer's own approved entries drafted from a photo or voice note (T11.10); the count."""
    # Nothing refers to the file they came from: it was never stored. Only a gymer writes, and
    # only their own rows; every other case is NotFound and writes nothing.
    try:
        user_id = values.user_id(user_id)
    except values.StoreValueError:
        raise NotFound from None
    rows = _rows(user_id, foods, weights, workouts)
    with transaction(conn):
        if role_of(conn, user_id) != "gymer":
            raise NotFound
        _write_rows(conn, rows)
    return len(foods) + len(weights) + len(workouts)
