"""The drafted mark of a gymer's message and the one-step write of its entries (T11.5)."""

import sqlite3
from datetime import UTC, date, datetime, timedelta

import pytest

from src.store import drafts, messages, my_data, records, users, values
from src.store.access import NotFound
from tests import store_world as world
from tests.store_world import no_threads

LONG_AGO = datetime(2000, 1, 1, tzinfo=UTC)
FOOD = drafts.DraftedFood(
    world.DAY, "breakfast", 9001, "Oats, raw", 80.0, 303.2, 10.5, 54.0, 5.3, 8.0
)
WEIGHT = drafts.DraftedWeight(81.4, world.DAY)
WORKOUT = drafts.DraftedWorkout(world.DAY, (records.ExerciseSet("squat", 1, 5, 100.0),))


@pytest.fixture
def conn(store_conn):
    """Build the store world with a short thread between coach A and the sharing gymer."""
    world.build(store_conn)
    return store_conn


def _thread(conn, gymer=world.SHARED):
    """Return the ID of the gymer's newest relationship."""
    return conn.execute(
        "SELECT id FROM coach_clients WHERE client_id = ? ORDER BY id DESC", (gymer,)
    ).fetchone()[0]


def _count(conn, table, user_id=world.SHARED):
    """Return how many rows of a record table belong to the user."""
    return conn.execute(f"SELECT count(*) FROM {table} WHERE user_id = ?", (user_id,)).fetchone()[0]


def _logged(conn):
    """Return the sharing gymer's counts of meals, weights and workouts."""
    return tuple(_count(conn, t) for t in ("meal_items", "body_measurements", "workout_sessions"))


def test_only_the_gymers_own_undrafted_messages_are_listed_oldest_first(conn):
    """The coach's messages and the drafted ones are left out; the limit keeps the oldest."""
    thread = _thread(conn)
    first = messages.send_message(conn, world.SHARED, thread, "Oats for breakfast.")
    messages.send_message(conn, world.COACH_A, thread, "Nice, 80 g?")
    second = messages.send_message(conn, world.SHARED, thread, "Yes, and I weigh 81.4 kg.")
    third = messages.send_message(conn, world.SHARED, thread, "Squats 5 x 100.")
    listed = drafts.undrafted_messages(conn, world.SHARED, thread, since=LONG_AGO, limit=10)
    assert [row["id"] for row in listed] == [first, second, third]
    assert drafts.mark_finished(conn, world.SHARED, second)
    listed = drafts.undrafted_messages(conn, world.SHARED, thread, since=LONG_AGO, limit=1)
    assert [row["id"] for row in listed] == [first]
    later = datetime.now(UTC) + timedelta(days=1)
    assert drafts.undrafted_messages(conn, world.SHARED, thread, since=later, limit=10) == []


@pytest.mark.parametrize(
    ("user", "relationship"),
    [
        (world.COACH_A, "shared"),  # the coach never gets the client's messages here
        (world.OTHERS, "shared"),
        (world.SHARED, "others"),
        (world.ENDED, "ended"),  # an ended thread is not drafted
        (world.MISSING, "shared"),
        ("", "shared"),
        (world.SHARED, "x"),
    ],
)
def test_listing_another_thread_or_an_ended_one_is_not_found(conn, user, relationship):
    """Every case but the gymer's own active thread is the same NotFound."""
    target = {
        "shared": _thread(conn),
        "others": _thread(conn, world.OTHERS),
        "ended": _thread(conn, world.ENDED),
    }.get(relationship, relationship)
    with pytest.raises(NotFound):
        drafts.undrafted_messages(conn, user, target, since=LONG_AGO, limit=10)


def test_a_step_logs_its_entries_and_marks_the_message_once(conn):
    """The step writes every approved entry and the mark; a second step writes nothing."""
    message = messages.send_message(conn, world.SHARED, _thread(conn), "Breakfast, weight, squats.")
    before = _logged(conn)
    entries = {"foods": [FOOD], "weights": [WEIGHT], "workouts": [WORKOUT]}
    assert drafts.save_step(conn, world.SHARED, message, **entries)
    assert _logged(conn) == tuple(count + 1 for count in before)
    row = conn.execute(
        "SELECT from_suggestion, from_recipe, grams, kcal FROM meal_items"
        " WHERE user_id = ? ORDER BY id DESC",
        (world.SHARED,),
    ).fetchone()
    assert tuple(row) == (0, None, 80.0, 303.2)  # neither from a suggestion nor from a recipe
    assert not drafts.save_step(conn, world.SHARED, message, **entries)  # another tab, say
    assert _logged(conn) == tuple(count + 1 for count in before)
    assert not drafts.mark_finished(conn, world.SHARED, message)


def test_a_step_with_every_card_rejected_only_marks_the_message(conn):
    """A step with no approved entry still finishes the message."""
    message = messages.send_message(conn, world.SHARED, _thread(conn), "Oats.")
    before = _logged(conn)
    assert drafts.save_step(conn, world.SHARED, message)
    assert _logged(conn) == before
    assert (
        drafts.undrafted_messages(conn, world.SHARED, _thread(conn), since=LONG_AGO, limit=5) == []
    )


def test_a_mark_that_fails_to_write_leaves_no_entry(conn):
    """If the drafted row's write fails, the step's entries are rolled back with it."""
    message = messages.send_message(conn, world.SHARED, _thread(conn), "Oats and squats.")
    before = _logged(conn)
    conn.execute(
        "CREATE TEMP TRIGGER fail_mark BEFORE INSERT ON message_drafts "
        "BEGIN SELECT RAISE(ABORT, 'mark refused'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="mark refused"):
        drafts.save_step(conn, world.SHARED, message, foods=[FOOD], workouts=[WORKOUT])
    assert _logged(conn) == before
    conn.execute("DROP TRIGGER fail_mark")
    assert len(
        drafts.undrafted_messages(conn, world.SHARED, _thread(conn), since=LONG_AGO, limit=5)
    )


def test_a_bad_entry_writes_nothing_and_leaves_the_message_undrafted(conn):
    """A value the record checks refuse stops the step before anything is written."""
    message = messages.send_message(conn, world.SHARED, _thread(conn), "Weighed in.")
    before = _logged(conn)
    with pytest.raises(values.StoreValueError):
        drafts.save_step(
            conn,
            world.SHARED,
            message,
            foods=[FOOD],
            weights=[drafts.DraftedWeight(9.0, world.DAY)],
        )
    assert _logged(conn) == before
    assert len(
        drafts.undrafted_messages(conn, world.SHARED, _thread(conn), since=LONG_AGO, limit=5)
    )


@pytest.mark.parametrize("who", [world.COACH_A, world.OTHERS, world.MISSING, ""])
def test_another_users_message_is_not_found_and_writes_nothing(conn, who):
    """Only the sender, a gymer, finishes or logs from their message."""
    message = messages.send_message(conn, world.SHARED, _thread(conn), "Oats.")
    for call in (drafts.mark_finished, drafts.save_step):
        with pytest.raises(NotFound):
            call(conn, who, message)
    with pytest.raises(NotFound):
        drafts.mark_finished(conn, world.SHARED, 999999)
    assert conn.execute("SELECT count(*) FROM message_drafts").fetchone()[0] == 0


def test_a_coachs_message_is_not_the_gymers_to_mark(conn):
    """The gymer cannot mark or log from the coach's message in their own thread."""
    message = messages.send_message(conn, world.COACH_A, _thread(conn), "Log your oats.")
    with pytest.raises(NotFound):
        drafts.mark_finished(conn, world.SHARED, message)


@pytest.mark.parametrize("deleting", [world.COACH_A, world.SHARED])
def test_each_sides_delete_succeeds_and_the_coachs_keeps_the_gymers_log(conn, deleting):
    """The marks go with the thread; the coach's delete leaves the gymer's logged entries."""
    message = messages.send_message(conn, world.SHARED, _thread(conn), "Oats.")
    drafts.save_step(conn, world.SHARED, message, foods=[FOOD], workouts=[WORKOUT])
    logged = _logged(conn)
    my_data.delete_user_data(conn, deleting, no_threads)
    assert conn.execute("SELECT count(*) FROM message_drafts").fetchone()[0] == 0
    if deleting == world.COACH_A:
        assert _logged(conn) == logged
    else:
        assert _logged(conn) == (0, 0, 0)


def test_a_future_day_is_refused_for_a_workout(conn):
    """A drafted workout keeps the store's rule: no day after today."""
    message = messages.send_message(conn, world.SHARED, _thread(conn), "Squats tomorrow.")
    future = drafts.DraftedWorkout(date.today() + timedelta(days=3), WORKOUT.sets)
    with pytest.raises(values.StoreValueError):
        drafts.save_step(conn, world.SHARED, message, workouts=[future])


def test_ending_the_relationship_keeps_the_marks_and_stops_the_listing(conn):
    """After the end, the thread lists nothing more, and nothing is unmarked."""
    thread = _thread(conn)
    message = messages.send_message(conn, world.SHARED, thread, "Oats.")
    drafts.mark_finished(conn, world.SHARED, message)
    users.end_relationship(conn, world.SHARED, thread)
    with pytest.raises(NotFound):
        drafts.undrafted_messages(conn, world.SHARED, thread, since=LONG_AGO, limit=5)
    assert conn.execute("SELECT count(*) FROM message_drafts").fetchone()[0] == 1


def _as_read(conn, message_id):
    """Return a message's thread and time as the workflow read them."""
    row = conn.execute(
        "SELECT relationship_id, created_at FROM messages WHERE id = ?", (message_id,)
    ).fetchone()
    return row["relationship_id"], row["created_at"]


@pytest.mark.parametrize(
    "case",
    [
        "another_gymer",
        "coach",
        "another_thread",
        "another_time",
        "time_not_text",
        "bad_id",
        "marked",
    ],
)
def test_a_message_not_as_read_is_not_still_undrafted(conn, case):
    """Only the gymer's own unmarked message, in its thread at its time, is still undrafted."""
    message = messages.send_message(conn, world.SHARED, _thread(conn), "Oats.")
    thread, sent = _as_read(conn, message)
    assert drafts.is_still_undrafted(conn, world.SHARED, thread, message, sent)
    user, args = world.SHARED, [thread, message, sent]
    if case == "another_gymer":
        user = world.OTHERS
    elif case == "coach":
        user = world.COACH_A
    elif case == "another_thread":
        args[0] = _thread(conn, world.OTHERS)
    elif case == "another_time":
        args[2] = "2000-01-01T00:00:00+00:00"
    elif case == "time_not_text":
        args[2] = None
    elif case == "bad_id":
        args[1] = "x"
    else:
        drafts.mark_finished(conn, world.SHARED, message)
    assert not drafts.is_still_undrafted(conn, user, *args)


@pytest.mark.parametrize("case", ["another_gymer", "coach", "ended", "bad_id", "bad_user"])
def test_only_the_gymers_own_active_thread_is_open(conn, case):
    """Another gymer's thread, the coach, an ended thread or a bad value is not open."""
    thread = _thread(conn)
    assert drafts.is_open_thread(conn, world.SHARED, thread)
    user = world.SHARED
    if case == "another_gymer":
        user = world.OTHERS
    elif case == "coach":
        user = world.COACH_A
    elif case == "ended":
        users.end_relationship(conn, world.SHARED, thread)
    elif case == "bad_id":
        thread = "x"
    else:
        user = ""
    assert not drafts.is_open_thread(conn, user, thread)


def test_a_step_for_a_reused_message_id_is_refused(conn):
    """A step names the message's time; a later row under the same ID is not that message."""
    message = messages.send_message(conn, world.SHARED, _thread(conn), "Oats.")
    with pytest.raises(NotFound):
        drafts.save_step(
            conn, world.SHARED, message, foods=[FOOD], created_at="2000-01-01T00:00:00+00:00"
        )
    assert conn.execute("SELECT count(*) FROM message_drafts").fetchone()[0] == 0
    _, sent = _as_read(conn, message)
    assert drafts.save_step(conn, world.SHARED, message, foods=[FOOD], created_at=sent)
