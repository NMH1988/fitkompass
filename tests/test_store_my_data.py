"""Export and delete everything about a user (T9.6, AC-34), with foreign keys on."""

import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from src.store import (
    access,
    ai_consents,
    db,
    meal_plans,
    messages,
    my_data,
    questions,
    records,
    reviews,
    suggestions,
    users,
)
from tests import store_world as world
from tests.store_world import no_threads

NOW = "2026-10-27T10:00:00+00:00"
SUGGESTED = suggestions.SuggestedFood("breakfast", 9001, "CANARY-FOOD oats", 80.0)
QUESTION = "CANARY-QUESTION why fewer carbs?"
ANSWER = "CANARY-ANSWER rest days need less."
MESSAGE = "CANARY-MESSAGE had oats and two eggs"
VERSION = "0123456789ab"
PLANNED = meal_plans.PlannedFood(
    "dinner", 9003, "CANARY-PLAN pasta", 400.0, 1480.0, 52.0, 300.0, 6.0
)


@pytest.fixture
def full_world(store_conn):
    """Build the world plus reviews, audit rows, an invitation and code attempts."""
    world.build(store_conn)
    review_args = {
        "period_start": date(2026, 10, 19),
        "metrics": {"logged_days": 3},
        "data_quality": {},
        "draft": {"observations": ["x"]},
        "model_version": "m",
        "prompt_version": "0123456789ab",
        "evidence_refs": [("12", "12-3")],
    }
    approved = reviews.save_review(store_conn, world.COACH_A, world.SHARED, **review_args)
    # Another week: a second review of a week that has a pending or approved one is refused.
    next_week = {**review_args, "period_start": date(2026, 10, 26)}
    reviews.save_review(store_conn, world.COACH_A, world.SHARED, **next_week)  # stays pending
    reviews.save_review(store_conn, world.COACH_B, world.OTHERS, **review_args)
    reviews.decide_review(store_conn, world.COACH_A, approved, "approve")
    records.list_meal_items(store_conn, world.COACH_A, world.SHARED)  # an audited read
    records.list_meal_items(store_conn, world.COACH_B, world.OTHERS)
    # T9.25: a question and the coach's answer under the approved review (an audited answer).
    questions.ask_question(store_conn, world.SHARED, approved, QUESTION)
    questions.answer_question(store_conn, world.COACH_A, approved, ANSWER)
    # T9.34: each coach suggests foods to their client (an audited suggestions_set each).
    for coach, client in ((world.COACH_A, world.SHARED), (world.COACH_B, world.OTHERS)):
        suggestions.add_client_suggestions(store_conn, coach, client, [SUGGESTED])
    # T11.7: each coach saves a meal plan for their client (an audited meal_plan_set each).
    for coach, client in ((world.COACH_A, world.SHARED), (world.COACH_B, world.OTHERS)):
        meal_plans.add_client_meal_plan(store_conn, coach, client, [PLANNED])
    # T11.3: a thread for each relationship. Coach A writes to the client who shares nothing, so
    # that client sends nothing; the ended thread's message is written as it was before the end.
    threads = {
        gymer: store_conn.execute(
            "SELECT id FROM coach_clients WHERE client_id = ?", (gymer,)
        ).fetchone()[0]
        for gymer in world.GYMERS
    }
    drafted = messages.send_message(store_conn, world.SHARED, threads[world.SHARED], MESSAGE)
    messages.send_message(store_conn, world.COACH_A, threads[world.SHARED], "Nice, log it.")
    messages.send_message(store_conn, world.COACH_A, threads[world.UNSHARED], "Welcome!")
    messages.send_message(store_conn, world.OTHERS, threads[world.OTHERS], "Coach B, hi.")
    store_conn.execute(
        "INSERT INTO messages (relationship_id, sender_id, text, created_at) VALUES (?, ?, ?, ?)",
        (threads[world.ENDED], world.ENDED, "Thanks for everything.", NOW),
    )
    # T11.5: the gymers' Art. 9 consents, (b) given to their coach, and a drafted message's mark.
    ai_consents.give(store_conn, world.SHARED, "message_drafts", VERSION)
    ai_consents.give(store_conn, world.SHARED, "coach_thread", VERSION, threads[world.SHARED])
    ai_consents.give(store_conn, world.OTHERS, "coach_thread", VERSION, threads[world.OTHERS])
    store_conn.execute("INSERT INTO message_drafts (message_id) VALUES (?)", (drafted,))
    # T9.12 adds the functions for these two tables; the rows are written directly here.
    for coach in (world.COACH_A, world.COACH_B):
        store_conn.execute(
            "INSERT INTO invitations (coach_id, code_hash, created_at, expires_at)"
            " VALUES (?, ?, ?, ?)",
            (coach, coach + "-hash", NOW, NOW),
        )
    for gymer in (world.SHARED, world.OTHERS):
        store_conn.execute(
            "INSERT INTO invite_attempts (user_id, day, count) VALUES (?, '2026-10-27', 2)",
            (gymer,),
        )
    return store_conn


def _user_columns(conn):
    """Return (table, column) for every column that refers to users(id), and users.id itself."""
    found = [("users", "id")]
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'"):
        for key in conn.execute(f"PRAGMA foreign_key_list({table})"):
            if key["table"] == "users":
                found.append((table, key["from"]))
    return found


def _rows_naming(conn, user_id):
    """Return {table: count} of rows that refer to the user in any user column."""
    counts = {}
    for table, column in _user_columns(conn):
        query = f"SELECT count(*) FROM {table} WHERE {column} = ?"
        count = conn.execute(query, (user_id,)).fetchone()[0]
        if count:
            counts[f"{table}.{column}"] = count
    return counts


def _all_rows(conn):
    """Return every row of every table, as {table: [tuples]}."""
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    return {
        t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY rowid")] for t in tables
    }


def test_the_store_has_the_columns_this_test_expects(full_world):
    """The scan of user columns finds every reference (a new one must be handled in my_data)."""
    assert set(_user_columns(full_world)) == {
        ("users", "id"),
        ("invitations", "coach_id"),
        ("coach_clients", "coach_id"),
        ("coach_clients", "client_id"),
        ("profile_entries", "user_id"),
        ("body_measurements", "user_id"),
        ("nutrition_targets", "user_id"),
        ("meal_items", "user_id"),
        ("workout_sessions", "user_id"),
        ("preferences", "user_id"),
        ("ai_reviews", "client_id"),
        ("ai_reviews", "coach_id"),
        ("ai_reviews", "reviewed_by"),
        ("audit_log", "actor_id"),
        ("audit_log", "subject_id"),
        ("invite_attempts", "user_id"),
        ("review_questions", "author_id"),
        ("notification_reads", "user_id"),
        ("food_suggestion_lists", "client_id"),
        ("food_suggestion_lists", "coach_id"),
        ("messages", "sender_id"),
        ("meal_plans", "client_id"),
        ("meal_plans", "coach_id"),
        ("ai_consents", "user_id"),
    }


def test_a_gymers_export_holds_a_rejection_but_not_the_rejected_review(full_world):
    """A rejected review stays out of the gymer's export; its review_rejected audit row is in it."""
    rejected = reviews.save_review(
        full_world,
        world.COACH_A,
        world.SHARED,
        period_start=date(2026, 10, 12),
        metrics={"logged_days": 2},
        data_quality={},
        draft={"observations": ["CANARY-REJECTED"]},
        model_version="m",
        prompt_version="0123456789ab",
    )
    reviews.decide_review(full_world, world.COACH_A, rejected, "reject")
    text = my_data.export_user_data(full_world, world.SHARED)
    document = json.loads(text)
    assert rejected not in [review["id"] for review in document["ai_reviews"]]
    assert "CANARY-REJECTED" not in text
    decisions = [
        (row["action"], row["resource_id"])
        for row in document["audit_log"]
        if row["action"].startswith("review_")
    ]
    assert ("review_rejected", rejected) in decisions


def test_a_gymers_export_holds_all_their_rows_as_json(full_world):
    """Every table appears; the gymer's records, relationship, scopes, approved review and audit."""
    document = json.loads(my_data.export_user_data(full_world, world.SHARED))
    tables = {
        r[0] for r in full_world.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert set(document) == (tables - {"users"}) | {"user"}
    assert document["user"]["id"] == world.SHARED
    for table in ("profile_entries", "body_measurements", "nutrition_targets", "meal_items"):
        assert len(document[table]) == 1 and document[table][0]["user_id"] == world.SHARED
    assert len(document["workout_sessions"]) == 1 and len(document["exercise_sets"]) == 2
    assert document["preferences"] == []  # only coaches keep preferences (T9.7)
    assert len(document["coach_clients"]) == 1 and len(document["consents"]) == 3
    assert [r["status"] for r in document["ai_reviews"]] == ["APPROVED"]
    assert document["ai_reviews"][0]["final"] == {"observations": ["x"]}
    # The version of the prompt that drafted it (T10.4).
    assert document["ai_reviews"][0]["prompt_version"] == "0123456789ab"
    assert len(document["ai_evidence_refs"]) == 1
    # The coach's read of the meals and the approval of the review, both about this gymer.
    assert [r["action"] for r in document["audit_log"]] == [
        "review_approved",
        "read",
        "review_answered",
        "suggestions_set",
        "meal_plan_set",
    ]
    assert [(r["kind"], r["text"]) for r in document["review_questions"]] == [
        ("question", QUESTION),
        ("answer", ANSWER),
    ]
    assert document["invite_attempts"][0]["count"] == 2
    assert document["invitations"] == []
    # T9.34: the list coach A suggested to this gymer, with its item; never coach B's.
    [listed] = document["food_suggestion_lists"]
    assert (listed["client_id"], listed["coach_id"]) == (world.SHARED, world.COACH_A)
    [item] = document["food_suggestion_items"]
    assert (item["list_id"], item["food_name"]) == (listed["id"], SUGGESTED.food_name)
    # T11.7: the plan coach A wrote for this gymer, with its item; never coach B's.
    [plan] = document["meal_plans"]
    assert (plan["client_id"], plan["coach_id"]) == (world.SHARED, world.COACH_A)
    [planned] = document["meal_plan_items"]
    assert (planned["plan_id"], planned["food_name"], planned["grams"]) == (
        plan["id"],
        PLANNED.food_name,
        PLANNED.grams,
    )
    # T11.3: the whole thread with coach A, both sides' messages.
    assert [(m["sender_id"], m["text"]) for m in document["messages"]] == [
        (world.SHARED, MESSAGE),
        (world.COACH_A, "Nice, log it."),
    ]


def test_a_coachs_export_holds_their_relationships_reviews_and_invitations(full_world):
    """A coach exports the reviews they wrote, pending ones too, and their invitations."""
    document = json.loads(my_data.export_user_data(full_world, world.COACH_A))
    assert document["user"]["role"] == "coach"
    assert len(document["coach_clients"]) == 3
    assert [r["status"] for r in document["ai_reviews"]] == ["APPROVED", "PENDING_REVIEW"]
    assert {r["prompt_version"] for r in document["ai_reviews"]} == {"0123456789ab"}  # T10.4
    assert len(document["invitations"]) == 1
    assert {r["actor_id"] for r in document["audit_log"]} == {world.COACH_A}
    assert document["meal_items"] == []
    # T9.34: the lists a coach wrote are their clients' data, so only their audit rows are here.
    assert document["food_suggestion_lists"] == [] and document["food_suggestion_items"] == []
    assert "suggestions_set" in {r["action"] for r in document["audit_log"]}
    # T11.7: likewise the plans a coach wrote: only their audit rows, no food or amount.
    assert document["meal_plans"] == [] and document["meal_plan_items"] == []
    assert "meal_plan_set" in {r["action"] for r in document["audit_log"]}


def _read_rows(conn):
    """Return (actor, subject, resource type) of every read in the audit log."""
    query = "SELECT actor_id, subject_id, resource_type FROM audit_log WHERE action = 'read'"
    return [tuple(row) for row in conn.execute(query)]


def test_a_coachs_export_audits_one_read_per_client_in_it(full_world):
    """The coach's export reads clients' reviews, so it writes a read row for each client."""
    before = _read_rows(full_world)
    my_data.export_user_data(full_world, world.COACH_A)
    added = _read_rows(full_world)[len(before) :]
    assert added == [
        (world.COACH_A, world.SHARED, "ai_reviews"),
        (world.COACH_A, world.SHARED, "review_questions"),
    ]


def test_a_gymers_export_writes_no_audit_row(full_world):
    """Reading one's own data is not audited."""
    before = _read_rows(full_world)
    my_data.export_user_data(full_world, world.SHARED)
    assert _read_rows(full_world) == before


def test_an_export_holds_no_other_users_records(full_world):
    """Another gymer's records and coach B's rows are not in the gymer's export."""
    text = my_data.export_user_data(full_world, world.SHARED)
    for other in (world.OTHERS, world.UNSHARED, world.ENDED, world.COACH_B):
        assert other not in text


def test_exporting_or_deleting_a_missing_user_is_not_found(full_world):
    """A user who does not exist gives NotFound."""
    with pytest.raises(access.NotFound):
        my_data.export_user_data(full_world, world.MISSING)
    with pytest.raises(access.NotFound):
        my_data.delete_user_data(full_world, world.MISSING, no_threads)


@pytest.mark.parametrize("user", [world.SHARED, world.COACH_A, world.OTHERS, world.ENDED])
def test_deleting_a_user_leaves_no_row_about_them_and_every_other_row(full_world, user):
    """After the delete no column names the user, references hold, and others' rows remain."""
    assert _rows_naming(full_world, user)
    before = _rows_naming(full_world, world.UNSHARED)
    my_data.delete_user_data(full_world, user, no_threads)
    assert _rows_naming(full_world, user) == {}
    assert full_world.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert full_world.execute("PRAGMA foreign_key_check").fetchall() == []
    # UNSHARED is coach A's client: deleting coach A also removes that relationship.
    after = _rows_naming(full_world, world.UNSHARED)
    if user == world.COACH_A:
        before.pop("coach_clients.client_id")
    assert after == before
    with pytest.raises(access.NotFound):
        my_data.delete_user_data(full_world, user, no_threads)


def test_deleting_a_gymer_removes_the_reviews_about_them(full_world):
    """Every review about the gymer goes, pending ones and their evidence included."""
    my_data.delete_user_data(full_world, world.SHARED, no_threads)
    assert full_world.execute("SELECT count(*) FROM ai_reviews").fetchone()[0] == 1  # coach B's
    assert full_world.execute("SELECT count(*) FROM ai_evidence_refs").fetchone()[0] == 1


def test_deleting_a_coach_removes_the_reviews_they_wrote_and_keeps_the_clients_records(full_world):
    """Coach A's reviews, relationships and invitation go; the clients' own records stay."""
    my_data.delete_user_data(full_world, world.COACH_A, no_threads)
    coaches = [row["coach_id"] for row in full_world.execute("SELECT coach_id FROM ai_reviews")]
    assert coaches == [world.COACH_B]
    assert full_world.execute("SELECT count(*) FROM consents").fetchone()[0] == 3  # coach B's
    assert records.list_meal_items(full_world, world.SHARED, world.SHARED)


@pytest.mark.parametrize("user", [world.SHARED, world.COACH_A])
def test_deleting_either_side_removes_their_suggestion_lists_and_items(full_world, user):
    """Coach A's list for SHARED goes with either side's data (T9.34); coach B's list stays."""
    suggestions.add_client_suggestions(
        full_world,
        world.COACH_A,
        world.SHARED,
        [SUGGESTED, suggestions.SuggestedFood("lunch", 9002, "Rice", 150.0)],
    )
    [item] = [
        i
        for i in suggestions.current_suggestions(full_world, world.SHARED, world.SHARED)["items"]
        if i["meal"] == "breakfast"
    ]
    if user == world.COACH_A:  # the client's flagged item stays with the client's records
        records.add_meal_item(
            full_world,
            world.SHARED,
            consumed_on=world.DAY,
            meal="breakfast",
            fdc_id=SUGGESTED.fdc_id,
            food_name=SUGGESTED.food_name,
            grams=80.0,
            kcal=300.0,
            protein_g=10.0,
            carbohydrate_g=50.0,
            fat_g=5.0,
            fiber_g=None,
            suggestion_item_id=item["id"],
        )
    my_data.delete_user_data(full_world, user, no_threads)
    lists = full_world.execute("SELECT client_id, coach_id FROM food_suggestion_lists").fetchall()
    assert [tuple(row) for row in lists] == [(world.OTHERS, world.COACH_B)]
    assert full_world.execute("SELECT count(*) FROM food_suggestion_items").fetchone()[0] == 1
    if user == world.COACH_A:
        flags = [
            r["from_suggestion"] for r in records.list_meal_items(full_world, *[world.SHARED] * 2)
        ]
        assert sorted(flags) == [0, 1]


@pytest.mark.parametrize("user", [world.SHARED, world.COACH_A])
def test_deleting_either_side_removes_their_meal_plans_and_items(full_world, user):
    """Coach A's plans for SHARED go with either side's data (T11.7); coach B's plan stays."""
    meal_plans.add_client_meal_plan(full_world, world.COACH_A, world.SHARED, [])  # a removal too
    my_data.delete_user_data(full_world, user, no_threads)
    plans = full_world.execute("SELECT client_id, coach_id FROM meal_plans").fetchall()
    assert [tuple(row) for row in plans] == [(world.OTHERS, world.COACH_B)]
    [item] = full_world.execute("SELECT food_name FROM meal_plan_items").fetchall()
    assert item[0] == PLANNED.food_name


def _store_bytes(path: Path) -> bytes:
    """Return the bytes of the store file and of its write-ahead log, if there is one."""
    wal = Path(f"{path}-wal")
    return path.read_bytes() + (wal.read_bytes() if wal.exists() else b"")


def _message_texts(document):
    """Return the texts of an export's messages, in order."""
    return [m["text"] for m in document["messages"]]


def test_both_sides_export_every_thread_they_are_a_side_of_and_no_other(full_world):
    """A coach exports each client's thread, ended ones too; a gymer only their own threads."""
    export = {
        user: json.loads(my_data.export_user_data(full_world, user))
        for user in (world.COACH_A, world.COACH_B, world.ENDED, world.UNSHARED)
    }
    assert _message_texts(export[world.COACH_A]) == [
        MESSAGE,
        "Nice, log it.",
        "Welcome!",
        "Thanks for everything.",
    ]
    assert _message_texts(export[world.COACH_B]) == ["Coach B, hi."]
    assert _message_texts(export[world.ENDED]) == ["Thanks for everything."]
    assert _message_texts(export[world.UNSHARED]) == ["Welcome!"]


def test_exporting_the_threads_writes_no_audit_row(full_world):
    """Thread reads are not audited, in the export too: a gymer's export adds no row at all."""
    before = full_world.execute("SELECT count(*) FROM audit_log").fetchone()[0]
    my_data.export_user_data(full_world, world.UNSHARED)  # coach A wrote to them; no review
    assert full_world.execute("SELECT count(*) FROM audit_log").fetchone()[0] == before


@pytest.mark.parametrize("user", [world.SHARED, world.COACH_A])
def test_deleting_either_side_removes_their_threads_and_keeps_the_others(full_world, user):
    """A thread goes with either side's data, both sides' messages; other threads stay whole."""
    my_data.delete_user_data(full_world, user, no_threads)
    left = [row[0] for row in full_world.execute("SELECT text FROM messages ORDER BY id")]
    if user == world.SHARED:
        assert left == ["Welcome!", "Coach B, hi.", "Thanks for everything."]
    else:
        assert left == ["Coach B, hi."]


def test_deleting_one_entry_leaves_its_value_in_neither_file(tmp_path):
    """After records.delete_record(), the deleted entry is gone from the file and its -wal file."""
    path = tmp_path / "s.sqlite3"
    with db.connect(path) as conn:
        world.build(conn)
        records.add_preference(conn, world.COACH_A, "CANARY-ONE-ENTRY-DELETED")
        [entry] = [
            p
            for p in records.list_preferences(conn, world.COACH_A, world.COACH_A)
            if p["text"] == "CANARY-ONE-ENTRY-DELETED"
        ]
        assert b"CANARY-ONE-ENTRY-DELETED" in _store_bytes(path)
        records.delete_record(conn, world.COACH_A, "preferences", entry["id"])
        # While the store is still open: the delete checkpointed the log after its commit.
        assert Path(f"{path}-wal").stat().st_size == 0
        assert b"CANARY-ONE-ENTRY-DELETED" not in _store_bytes(path)


def test_deleted_values_are_gone_from_the_files_bytes(tmp_path):
    """After delete_user_data(), the deleted text is in neither the file nor its -wal file."""
    path = tmp_path / "s.sqlite3"
    with db.connect(path) as conn:
        world.build(conn)
        records.add_preference(conn, world.COACH_A, "CANARY-PREF-DELETED")
        thread = conn.execute(
            "SELECT id FROM coach_clients WHERE client_id = ?", (world.SHARED,)
        ).fetchone()[0]
        messages.send_message(conn, world.SHARED, thread, "CANARY-MESSAGE-DELETED")
        records.add_meal_item(
            conn,
            world.SHARED,
            consumed_on=date(2026, 10, 27),
            meal="dinner",
            fdc_id=7,
            food_name="CANARY-FOOD-DELETED",
            grams=100.0,
            kcal=100.0,
            protein_g=1.0,
            carbohydrate_g=1.0,
            fat_g=1.0,
            fiber_g=None,
        )
        before = _store_bytes(path)  # the checks below can fail
        assert b"CANARY-FOOD-DELETED" in before and b"CANARY-PREF-DELETED" in before
        assert b"CANARY-MESSAGE-DELETED" in before
        my_data.delete_user_data(conn, world.SHARED, no_threads)
        my_data.delete_user_data(conn, world.COACH_A, no_threads)
        # Other users' rows are still there, so the pages were reused, not dropped.
        assert records.list_preferences(conn, world.COACH_B, world.COACH_B)
        # While the store is still open (as the app and the chat server keep it): the delete
        # checkpointed the log, so no earlier copy of a deleted row is left in the -wal file.
        assert Path(f"{path}-wal").stat().st_size == 0
        data = _store_bytes(path)
        assert b"CANARY-PREF-DELETED" not in data and b"CANARY-FOOD-DELETED" not in data
        assert b"CANARY-MESSAGE-DELETED" not in data
    data = _store_bytes(path)
    assert b"CANARY-PREF-DELETED" not in data and b"CANARY-FOOD-DELETED" not in data
    assert b"CANARY-MESSAGE-DELETED" not in data
    assert not (tmp_path / "s.sqlite3-journal").exists()


def test_a_table_the_delete_forgets_makes_it_fail_and_change_nothing(full_world):
    """A new table referring to users, not in the delete, stops it: no partial delete is left."""
    full_world.execute("CREATE TABLE notes (user_id TEXT NOT NULL REFERENCES users (id)) STRICT")
    full_world.execute("INSERT INTO notes (user_id) VALUES (?)", (world.SHARED,))
    before = _all_rows(full_world)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        my_data.delete_user_data(full_world, world.SHARED, no_threads)
    assert _all_rows(full_world) == before


def test_a_coachs_export_holds_their_preferences_and_delete_removes_them(store_conn):
    """A coach's preferences are in their export and gone after "delete everything" (AC-34)."""
    world.build(store_conn)
    records.add_preference(store_conn, world.COACH_A, "most of my clients are vegetarian")
    document = json.loads(my_data.export_user_data(store_conn, world.COACH_A))
    assert [row["text"] for row in document["preferences"]] == [
        world.PREFERENCE,
        "most of my clients are vegetarian",
    ]
    assert {row["user_id"] for row in document["preferences"]} == {world.COACH_A}
    my_data.delete_user_data(store_conn, world.COACH_A, no_threads)
    count = "SELECT count(*) FROM preferences WHERE user_id = ?"
    assert store_conn.execute(count, (world.COACH_A,)).fetchone()[0] == 0
    assert records.list_preferences(store_conn, world.COACH_B, world.COACH_B)


@pytest.mark.parametrize("user", [world.SHARED, world.COACH_A])
def test_both_sides_export_the_target_set_row_and_the_gymer_the_target(full_world, user):
    """A coach's target is in the gymer's export; its audit row is in both sides' (T9.17)."""
    target_id = records.add_client_target(
        full_world,
        world.COACH_A,
        world.SHARED,
        kcal=2100.0,
        protein_g=170.0,
        carbs_g=200.0,
        fat_g=65.0,
        effective_from=date(2026, 10, 27),
    )
    document = json.loads(my_data.export_user_data(full_world, user))
    rows = [row for row in document["audit_log"] if row["action"] == "target_set"]
    assert [(row["resource_id"], row["subject_id"]) for row in rows] == [(target_id, world.SHARED)]
    if user == world.SHARED:
        targets = {row["id"]: row["set_by"] for row in document["nutrition_targets"]}
        assert targets[target_id] == "coach"


# --- The questions to the coach (T9.25, AC-42) ----------------------------------------------------


def _thread_texts(document):
    """Return the texts of the thread rows in an export."""
    return [row["text"] for row in document["review_questions"]]


def test_a_coachs_export_holds_the_threads_they_may_read(full_world):
    """The coach exports the thread under the review they wrote; another coach does not."""
    document = json.loads(my_data.export_user_data(full_world, world.COACH_A))
    assert _thread_texts(document) == [QUESTION, ANSWER]
    other = json.loads(my_data.export_user_data(full_world, world.COACH_B))
    assert other["review_questions"] == []
    assert QUESTION not in json.dumps(other)


def test_a_coachs_export_leaves_out_a_thread_once_the_client_stops_sharing(full_world):
    """With nutrition off (or the relationship ended), the coach's export holds no thread."""
    [relationship] = users.list_relationships(full_world, world.SHARED)
    users.set_consent(full_world, world.SHARED, relationship["id"], "nutrition", False)
    document = json.loads(my_data.export_user_data(full_world, world.COACH_A))
    assert document["review_questions"] == []
    gymer = json.loads(my_data.export_user_data(full_world, world.SHARED))
    assert _thread_texts(gymer) == [QUESTION, ANSWER]


def test_a_gymers_export_keeps_the_thread_after_the_end(full_world):
    """The gymer still reads the thread once the relationship ends (owner's choice, 2026-11-06)."""
    [relationship] = users.list_relationships(full_world, world.SHARED)
    users.end_relationship(full_world, world.SHARED, relationship["id"])
    document = json.loads(my_data.export_user_data(full_world, world.SHARED))
    assert _thread_texts(document) == [QUESTION, ANSWER]


@pytest.mark.parametrize("user", [world.SHARED, world.COACH_A])
def test_deleting_either_side_removes_the_thread(full_world, user):
    """The thread goes with its review, whoever deletes; its text is gone from the table."""
    my_data.delete_user_data(full_world, user, no_threads)
    assert full_world.execute("SELECT count(*) FROM review_questions").fetchone()[0] == 0


def test_deleting_a_user_removes_every_row_they_wrote(full_world):
    """A row by the user under another user's review goes too (no reference is left)."""
    reviewed = full_world.execute(
        "SELECT id FROM ai_reviews WHERE coach_id = ? AND status = 'APPROVED'", (world.COACH_A,)
    ).fetchone()[0]
    # Written directly: no store function lets a third user write here; the delete must still hold.
    full_world.execute(
        "INSERT INTO review_questions (review_id, author_id, kind, text, created_at)"
        " VALUES (?, ?, 'question', 'x', ?)",
        (reviewed, world.OTHERS, NOW),
    )
    my_data.delete_user_data(full_world, world.OTHERS, no_threads)
    count = "SELECT count(*) FROM review_questions WHERE author_id = ?"
    assert full_world.execute(count, (world.OTHERS,)).fetchone()[0] == 0
    assert full_world.execute("SELECT count(*) FROM review_questions").fetchone()[0] == 2


# --- Art. 9 consents and drafted marks (T11.5) ----------------------------------------------------


def _purposes(rows):
    """Return the (purpose, has a relationship) pairs of exported consent rows."""
    return sorted((row["purpose"], row["relationship_id"] is not None) for row in rows)


def test_only_the_gymers_export_holds_their_consents_and_drafted_marks(full_world):
    """The gymer exports every consent row and their drafted messages; the coach exports neither."""
    gymer = json.loads(my_data.export_user_data(full_world, world.SHARED))
    assert _purposes(gymer["ai_consents"]) == [("coach_thread", True), ("message_drafts", False)]
    assert len(gymer["message_drafts"]) == 1
    coach = json.loads(my_data.export_user_data(full_world, world.COACH_A))
    assert coach["ai_consents"] == [] and coach["message_drafts"] == []


def test_a_withdrawn_and_given_again_consent_exports_its_history(full_world):
    """Withdrawing and giving again keeps both rows, the first with its withdrawal time."""
    ai_consents.withdraw(full_world, world.SHARED, "message_drafts")
    ai_consents.give(full_world, world.SHARED, "message_drafts", VERSION)
    rows = json.loads(my_data.export_user_data(full_world, world.SHARED))["ai_consents"]
    drafts = [row for row in rows if row["purpose"] == "message_drafts"]
    assert [row["withdrawn_at"] is None for row in drafts] == [False, True]


def test_a_coachs_delete_removes_the_consent_given_to_them_and_keeps_the_gymers_log(full_world):
    """The coach's delete takes (b) and the drafted mark with the thread; (a) and the log stay."""
    meals_before = full_world.execute(
        "SELECT count(*) FROM meal_items WHERE user_id = ?", (world.SHARED,)
    ).fetchone()[0]
    my_data.delete_user_data(full_world, world.COACH_A, no_threads)
    rows = full_world.execute(
        "SELECT purpose FROM ai_consents WHERE user_id = ?", (world.SHARED,)
    ).fetchall()
    assert [row["purpose"] for row in rows] == ["message_drafts"]
    assert full_world.execute("SELECT count(*) FROM message_drafts").fetchone()[0] == 0
    meals_after = full_world.execute(
        "SELECT count(*) FROM meal_items WHERE user_id = ?", (world.SHARED,)
    ).fetchone()[0]
    assert meals_after == meals_before > 0
    others = full_world.execute(
        "SELECT count(*) FROM ai_consents WHERE user_id = ?", (world.OTHERS,)
    ).fetchone()[0]
    assert others == 1


def test_a_gymers_delete_removes_their_consents_and_drafted_marks(full_world):
    """The gymer's delete removes every consent row of theirs and their messages' marks."""
    my_data.delete_user_data(full_world, world.SHARED, no_threads)
    mine = full_world.execute(
        "SELECT count(*) FROM ai_consents WHERE user_id = ?", (world.SHARED,)
    ).fetchone()[0]
    assert mine == 0
    assert full_world.execute("SELECT count(*) FROM message_drafts").fetchone()[0] == 0
