"""Everything the store holds about a user: exported as JSON, or deleted (T9.6, AC-34).

The export holds the user's own rows in every table, the relationships and scopes they are part
of, the reviews they may read (a gymer's approved reviews about them without the model's draft, a
coach's own reviews of clients who still share nutrition and every other scope each review used,
with the reviews' evidence and scopes), the questions to the coach and the answers under the
approved ones among them (T9.25), the audit rows by or about them, the user's own notification
read mark (T9.29; never the other side's), the foods coaches suggested to them (T9.34), every
message of the threads they are a side of, both sides' messages, ended relationships' too (T11.3),
the meal plans coaches wrote for them (T11.7), a coach's own recipes with every version and food,
and a gymer's own ratings of recipes (T11.8; never the other side's), and the user's Art. 9
consents with their history and which of their messages the drafting workflow has finished with
(T11.5).
The delete removes the user's rows in every table, their relationships and scopes, the reviews about
them and those they wrote as a coach (with their evidence, questions and answers), every question or
answer the user wrote, the lists of suggested foods between the user and a coach or client (T9.34)
and the meal plans between them (T11.7), a coach's recipes with their versions, foods and every
client's rating of them, and the ratings the user gave (T11.8; the meal items gymers logged from a
deleted recipe stay theirs), the messages of every thread the user is a side of (T11.3),
so a thread goes when either side deletes their data, with its messages' drafted marks, the
Art. 9 consents of the user and those given to one coach that name the user's relationships
(T11.5), the invitations and code attempts, the read
mark, and the audit rows by or about them: the app is local and keeps no audit duty (the owner may
change this). It runs in one transaction with foreign keys on, and no reference cascades, so a table
this list forgets makes the delete fail instead of leaving rows behind. The review workflow's
threads in its checkpointer file go too, through the caller's `delete_threads` (T9.16). After the
commit the store's write-ahead log is checkpointed and emptied, so the deleted rows' earlier copies
are not left in its `-wal` file.
"""

import json
import sqlite3
from collections.abc import Callable

from src.store import values
from src.store.access import NotFound, audit, role_of
from src.store.db import checkpoint, transaction

_USER = "SELECT * FROM users WHERE id = ?"
_PROFILES = "SELECT * FROM profile_entries WHERE user_id = ? ORDER BY id"
_WEIGHTS = "SELECT * FROM body_measurements WHERE user_id = ? ORDER BY id"
_TARGETS = "SELECT * FROM nutrition_targets WHERE user_id = ? ORDER BY id"
_MEALS = "SELECT * FROM meal_items WHERE user_id = ? ORDER BY id"
_SESSIONS = "SELECT * FROM workout_sessions WHERE user_id = ? ORDER BY id"
_SETS = """
SELECT exercise_set.* FROM exercise_sets AS exercise_set
JOIN workout_sessions AS session ON session.id = exercise_set.session_id
WHERE session.user_id = ? ORDER BY exercise_set.id
"""
_PREFERENCES = "SELECT * FROM preferences WHERE user_id = ? ORDER BY id"
_INVITATIONS = "SELECT * FROM invitations WHERE coach_id = ? ORDER BY id"
_ATTEMPTS = "SELECT * FROM invite_attempts WHERE user_id = ? ORDER BY day"
_RELATIONSHIPS = """
SELECT * FROM coach_clients WHERE coach_id = ? OR client_id = ? ORDER BY id
"""
_CONSENTS = """
SELECT consent.* FROM consents AS consent
JOIN coach_clients AS relationship ON relationship.id = consent.relationship_id
WHERE relationship.coach_id = ? OR relationship.client_id = ? ORDER BY consent.id
"""
# What each reads (reviews.list_reviews()): a gymer the approved reviews about them without the
# model's draft, a coach the reviews they wrote about clients who still share nutrition with them
# and every other scope each review used (T9.16).
_APPROVED_ABOUT = """
SELECT id, client_id, coach_id, period_start, metrics, data_quality, NULL AS draft, final, status,
    edited_by_coach, model_version, prompt_version, created_at, reviewed_by, reviewed_at
FROM ai_reviews WHERE client_id = ? AND status = 'APPROVED' ORDER BY id
"""
_WRITTEN_FOR_SHARED = """
SELECT review.* FROM ai_reviews AS review
WHERE review.coach_id = ? AND EXISTS (
    SELECT 1 FROM open_shares AS share
    WHERE share.coach_id = review.coach_id AND share.client_id = review.client_id
      AND share.scope = 'nutrition'
)
    AND NOT EXISTS (
        SELECT 1 FROM ai_review_scopes AS used
        WHERE used.review_id = review.id AND NOT EXISTS (
            SELECT 1 FROM open_shares AS share
            WHERE share.coach_id = review.coach_id AND share.client_id = review.client_id
              AND share.scope = used.scope
        )
    )
ORDER BY review.id
"""
_EVIDENCE = """
SELECT ref.* FROM ai_evidence_refs AS ref
JOIN ai_reviews AS review ON review.id = ref.review_id
WHERE (review.client_id = ? AND review.status = 'APPROVED')
    OR (review.coach_id = ? AND EXISTS (
    SELECT 1 FROM open_shares AS share
    WHERE share.coach_id = review.coach_id AND share.client_id = review.client_id
      AND share.scope = 'nutrition'
)
    AND NOT EXISTS (
        SELECT 1 FROM ai_review_scopes AS used
        WHERE used.review_id = review.id AND NOT EXISTS (
            SELECT 1 FROM open_shares AS share
            WHERE share.coach_id = review.coach_id AND share.client_id = review.client_id
              AND share.scope = used.scope
        )
    )
)
ORDER BY ref.id
"""
# The scopes of the reviews the export holds, by the same rule.
_REVIEW_SCOPES = """
SELECT kept.* FROM ai_review_scopes AS kept
JOIN ai_reviews AS review ON review.id = kept.review_id
WHERE (review.client_id = ? AND review.status = 'APPROVED')
    OR (review.coach_id = ? AND EXISTS (
    SELECT 1 FROM open_shares AS share
    WHERE share.coach_id = review.coach_id AND share.client_id = review.client_id
      AND share.scope = 'nutrition'
)
    AND NOT EXISTS (
        SELECT 1 FROM ai_review_scopes AS used
        WHERE used.review_id = review.id AND NOT EXISTS (
            SELECT 1 FROM open_shares AS share
            WHERE share.coach_id = review.coach_id AND share.client_id = review.client_id
              AND share.scope = used.scope
        )
    )
)
ORDER BY kept.review_id, kept.scope
"""
# The questions to the coach and the answers (T9.25), by the rule of the review they belong to:
# a gymer's under the approved reviews about them, a coach's under the approved reviews they
# wrote about clients who still share nutrition and every other scope each review used.
_GYMER_QUESTIONS = """
SELECT question.* FROM review_questions AS question
JOIN ai_reviews AS review ON review.id = question.review_id
WHERE review.client_id = ? AND review.status = 'APPROVED'
ORDER BY question.id
"""
# The coach's rule is the review's own: the same clauses as reviews._WRITTEN_FOR_SHARED and
# questions._OF_COACH_ALL, written out here as a read cannot open a transaction inside the export's.
_COACH_QUESTIONS = """
SELECT question.*, review.client_id AS asked_by FROM review_questions AS question
JOIN ai_reviews AS review ON review.id = question.review_id
WHERE review.coach_id = ? AND review.status = 'APPROVED' AND EXISTS (
    SELECT 1 FROM open_shares AS share
    WHERE share.coach_id = review.coach_id AND share.client_id = review.client_id
      AND share.scope = 'nutrition'
)
    AND NOT EXISTS (
        SELECT 1 FROM ai_review_scopes AS used
        WHERE used.review_id = review.id AND NOT EXISTS (
            SELECT 1 FROM open_shares AS share
            WHERE share.coach_id = review.coach_id AND share.client_id = review.client_id
              AND share.scope = used.scope
        )
    )
ORDER BY question.id
"""
_AUDIT = "SELECT * FROM audit_log WHERE actor_id = ? OR subject_id = ? ORDER BY id"
# The reader's own read mark (T9.29): never another user's, so the other side of a relationship
# never learns whether or when a notification was read.
_READ_MARKS = "SELECT * FROM notification_reads WHERE user_id = ? ORDER BY id"
# The foods coaches suggested to the user as a client (T9.34), a former coach's hidden list too;
# never the lists a coach wrote, which are their clients' data.
_SUGGESTION_LISTS = "SELECT * FROM food_suggestion_lists WHERE client_id = ? ORDER BY id"
_SUGGESTION_ITEMS = """
SELECT item.* FROM food_suggestion_items AS item
JOIN food_suggestion_lists AS list ON list.id = item.list_id
WHERE list.client_id = ? ORDER BY item.id
"""
# The coaches' meal plans for the user as a client (T11.7), a former coach's hidden plan too; never
# the plans a coach wrote, which are their clients' data.
_MEAL_PLANS = "SELECT * FROM meal_plans WHERE client_id = ? ORDER BY id"
_MEAL_PLAN_ITEMS = """
SELECT item.* FROM meal_plan_items AS item
JOIN meal_plans AS plan ON plan.id = item.plan_id
WHERE plan.client_id = ? ORDER BY item.id
"""
# A coach's own recipes, every version and food (T11.8): the coach's content. The ratings of them
# are the gymers' data, in the gymers' exports only.
_RECIPES = "SELECT * FROM recipes WHERE coach_id = ? ORDER BY id"
_RECIPE_VERSIONS = """
SELECT version.* FROM recipe_versions AS version
JOIN recipes AS recipe ON recipe.id = version.recipe_id
WHERE recipe.coach_id = ? ORDER BY version.id
"""
_RECIPE_INGREDIENTS = """
SELECT ingredient.* FROM recipe_ingredients AS ingredient
JOIN recipe_versions AS version ON version.id = ingredient.version_id
JOIN recipes AS recipe ON recipe.id = version.recipe_id
WHERE recipe.coach_id = ? ORDER BY ingredient.id
"""
# The ratings the user gave as a client (T11.8).
_RATINGS = "SELECT * FROM recipe_ratings WHERE client_id = ? ORDER BY id"
# The messages of every thread the user is a side of, active or ended, both sides' (T11.3): both
# sides read the whole thread, so both exports hold it.
_MESSAGES = """
SELECT message.* FROM messages AS message
JOIN coach_clients AS relationship ON relationship.id = message.relationship_id
WHERE relationship.coach_id = ? OR relationship.client_id = ? ORDER BY message.id
"""
# The gymer's own Art. 9 consents, every row: the open ones and their history (T11.5).
_AI_CONSENTS = "SELECT * FROM ai_consents WHERE user_id = ? ORDER BY id"
# Which of the user's own messages the drafting workflow has finished with (T11.5).
_MESSAGE_DRAFTS = """
SELECT drafted.* FROM message_drafts AS drafted
JOIN messages AS message ON message.id = drafted.message_id
WHERE message.sender_id = ? ORDER BY drafted.message_id
"""

# The delete, children before parents. The threads under the reviews about or by the user go with
# them, and every question or answer the user wrote (T9.25).
_DELETE_QUESTIONS = """
DELETE FROM review_questions
WHERE author_id = ?
    OR review_id IN (SELECT id FROM ai_reviews WHERE client_id = ? OR coach_id = ?)
"""
_DELETE_EVIDENCE = """
DELETE FROM ai_evidence_refs
WHERE review_id IN (SELECT id FROM ai_reviews WHERE client_id = ? OR coach_id = ?)
"""
_DELETE_REVIEW_SCOPES = """
DELETE FROM ai_review_scopes
WHERE review_id IN (SELECT id FROM ai_reviews WHERE client_id = ? OR coach_id = ?)
"""
_DELETE_REVIEWS = "DELETE FROM ai_reviews WHERE client_id = ? OR coach_id = ?"
# The suggested foods between the user and a coach or client, whichever side the user is (T9.34).
_DELETE_SUGGESTION_ITEMS = """
DELETE FROM food_suggestion_items
WHERE list_id IN (SELECT id FROM food_suggestion_lists WHERE client_id = ? OR coach_id = ?)
"""
_DELETE_SUGGESTION_LISTS = "DELETE FROM food_suggestion_lists WHERE client_id = ? OR coach_id = ?"
# The meal plans between the user and a coach or client, whichever side the user is (T11.7).
_DELETE_MEAL_PLAN_ITEMS = """
DELETE FROM meal_plan_items
WHERE plan_id IN (SELECT id FROM meal_plans WHERE client_id = ? OR coach_id = ?)
"""
_DELETE_MEAL_PLANS = "DELETE FROM meal_plans WHERE client_id = ? OR coach_id = ?"
# The ratings the user gave and every rating of the user's recipes, then the recipes' foods,
# versions and the recipes (T11.8). meal_items.from_recipe has no foreign key, so a gymer's logged
# meals stay as they are when their coach's recipes go.
_DELETE_RATINGS = """
DELETE FROM recipe_ratings
WHERE client_id = ? OR recipe_id IN (SELECT id FROM recipes WHERE coach_id = ?)
"""
_DELETE_RECIPE_INGREDIENTS = """
DELETE FROM recipe_ingredients
WHERE version_id IN (
    SELECT version.id FROM recipe_versions AS version
    JOIN recipes AS recipe ON recipe.id = version.recipe_id
    WHERE recipe.coach_id = ?
)
"""
_DELETE_RECIPE_VERSIONS = """
DELETE FROM recipe_versions WHERE recipe_id IN (SELECT id FROM recipes WHERE coach_id = ?)
"""
_DELETE_RECIPES = "DELETE FROM recipes WHERE coach_id = ?"
# The workflow threads of the reviews about the user or by them (T9.16), deleted with them.
_THREADS = """
SELECT thread_id FROM ai_reviews
WHERE (client_id = ? OR coach_id = ?) AND thread_id IS NOT NULL ORDER BY id
"""
_DELETE_AUDIT = "DELETE FROM audit_log WHERE actor_id = ? OR subject_id = ?"
# Every thread the user is a side of, with both sides' messages (T11.3), and any message the user
# sent (always in one of those threads; named too, so the delete never depends on it).
_DELETE_MESSAGES = """
DELETE FROM messages
WHERE sender_id = ?
    OR relationship_id IN (SELECT id FROM coach_clients WHERE coach_id = ? OR client_id = ?)
"""
# The drafted marks of the messages deleted below (T11.5): the same messages, so the marks go first.
_DELETE_MESSAGE_DRAFTS = """
DELETE FROM message_drafts
WHERE message_id IN (
    SELECT id FROM messages
    WHERE sender_id = ?
        OR relationship_id IN (SELECT id FROM coach_clients WHERE coach_id = ? OR client_id = ?)
)
"""
# The user's Art. 9 consents, and the ones given to the user as a coach, which name a relationship
# deleted below (T11.5): a consent to one coach goes with that relationship.
_DELETE_AI_CONSENTS = """
DELETE FROM ai_consents
WHERE user_id = ?
    OR relationship_id IN (SELECT id FROM coach_clients WHERE coach_id = ? OR client_id = ?)
"""
_DELETE_CONSENTS = """
DELETE FROM consents
WHERE relationship_id IN (SELECT id FROM coach_clients WHERE coach_id = ? OR client_id = ?)
"""
_DELETE_RELATIONSHIPS = "DELETE FROM coach_clients WHERE coach_id = ? OR client_id = ?"
_DELETE_INVITATIONS = "DELETE FROM invitations WHERE coach_id = ?"
_DELETE_ATTEMPTS = "DELETE FROM invite_attempts WHERE user_id = ?"
_DELETE_SETS = """
DELETE FROM exercise_sets
WHERE session_id IN (SELECT id FROM workout_sessions WHERE user_id = ?)
"""
_DELETE_SESSIONS = "DELETE FROM workout_sessions WHERE user_id = ?"
_DELETE_MEALS = "DELETE FROM meal_items WHERE user_id = ?"
_DELETE_TARGETS = "DELETE FROM nutrition_targets WHERE user_id = ?"
_DELETE_WEIGHTS = "DELETE FROM body_measurements WHERE user_id = ?"
_DELETE_PROFILES = "DELETE FROM profile_entries WHERE user_id = ?"
_DELETE_PREFERENCES = "DELETE FROM preferences WHERE user_id = ?"
_DELETE_READ_MARKS = "DELETE FROM notification_reads WHERE user_id = ?"
_DELETE_USER = "DELETE FROM users WHERE id = ?"
_REVIEW_JSON = ("metrics", "data_quality", "draft", "final")


def _review(row: sqlite3.Row) -> dict:
    """Return a review row with its JSON fields decoded, so the export is one JSON document."""
    review = dict(row)
    for field in _REVIEW_JSON:
        if review[field] is not None:
            review[field] = json.loads(review[field])
    return review


def export_user_data(conn: sqlite3.Connection, user_id: str) -> str:
    """Return the user's rows as one JSON document, auditing a coach's read of client reviews."""
    user_id = values.user_id(user_id)
    one = (user_id,)
    both = (user_id, user_id)
    with transaction(conn):
        if role_of(conn, user_id) is None:
            raise NotFound
        written = conn.execute(_WRITTEN_FOR_SHARED, one).fetchall()
        # A coach's export reads clients' review data: audited per client, as list_reviews() is.
        for client_id in dict.fromkeys(row["client_id"] for row in written):
            audit(conn, user_id, "read", "ai_reviews", subject_id=client_id)
        # The threads under those reviews are read too (T9.25): audited per client, as
        # questions.list_questions() is.
        coach_questions = [dict(r) for r in conn.execute(_COACH_QUESTIONS, one)]
        for client_id in dict.fromkeys(row.pop("asked_by") for row in coach_questions):
            audit(conn, user_id, "read", "review_questions", subject_id=client_id)
        document = {
            "user": dict(conn.execute(_USER, one).fetchone()),
            "profile_entries": [dict(r) for r in conn.execute(_PROFILES, one)],
            "body_measurements": [dict(r) for r in conn.execute(_WEIGHTS, one)],
            "nutrition_targets": [dict(r) for r in conn.execute(_TARGETS, one)],
            "meal_items": [dict(r) for r in conn.execute(_MEALS, one)],
            "workout_sessions": [dict(r) for r in conn.execute(_SESSIONS, one)],
            "exercise_sets": [dict(r) for r in conn.execute(_SETS, one)],
            "preferences": [dict(r) for r in conn.execute(_PREFERENCES, one)],
            "invitations": [dict(r) for r in conn.execute(_INVITATIONS, one)],
            "invite_attempts": [dict(r) for r in conn.execute(_ATTEMPTS, one)],
            "coach_clients": [dict(r) for r in conn.execute(_RELATIONSHIPS, both)],
            "consents": [dict(r) for r in conn.execute(_CONSENTS, both)],
            "ai_reviews": [
                *(_review(r) for r in conn.execute(_APPROVED_ABOUT, one)),
                *(_review(r) for r in written),
            ],
            "ai_evidence_refs": [dict(r) for r in conn.execute(_EVIDENCE, both)],
            "ai_review_scopes": [dict(r) for r in conn.execute(_REVIEW_SCOPES, both)],
            "review_questions": [
                *(dict(r) for r in conn.execute(_GYMER_QUESTIONS, one)),
                *coach_questions,
            ],
            "audit_log": [dict(r) for r in conn.execute(_AUDIT, both)],
            "notification_reads": [dict(r) for r in conn.execute(_READ_MARKS, one)],
            "food_suggestion_lists": [dict(r) for r in conn.execute(_SUGGESTION_LISTS, one)],
            "food_suggestion_items": [dict(r) for r in conn.execute(_SUGGESTION_ITEMS, one)],
            "messages": [dict(r) for r in conn.execute(_MESSAGES, both)],
            "meal_plans": [dict(r) for r in conn.execute(_MEAL_PLANS, one)],
            "meal_plan_items": [dict(r) for r in conn.execute(_MEAL_PLAN_ITEMS, one)],
            "recipes": [dict(r) for r in conn.execute(_RECIPES, one)],
            "recipe_versions": [dict(r) for r in conn.execute(_RECIPE_VERSIONS, one)],
            "recipe_ingredients": [dict(r) for r in conn.execute(_RECIPE_INGREDIENTS, one)],
            "recipe_ratings": [dict(r) for r in conn.execute(_RATINGS, one)],
            "ai_consents": [dict(r) for r in conn.execute(_AI_CONSENTS, one)],
            "message_drafts": [dict(r) for r in conn.execute(_MESSAGE_DRAFTS, one)],
        }
    return json.dumps(document, ensure_ascii=False, indent=2)


def delete_user_data(
    conn: sqlite3.Connection,
    user_id: str,
    delete_threads: Callable[[list[str]], None],
) -> None:
    """Delete the user and every row about them, in one transaction; NotFound if there is none."""
    # delete_threads (T9.16) gets the threads of the user's reviews and deletes them, and every
    # other thread about or by the user, from the checkpointer file (src/agent/review_threads.py;
    # the store imports no LangGraph). It runs last, inside the transaction, even with no thread
    # listed (a crashed run leaves one with no review): if it fails, no row is deleted and the user
    # can try again. It is required, so no caller can report a deletion that left the threads'
    # copies of a client's week behind.
    user_id = values.user_id(user_id)
    one = (user_id,)
    both = (user_id, user_id)
    with transaction(conn):
        if role_of(conn, user_id) is None:
            raise NotFound
        threads = [row["thread_id"] for row in conn.execute(_THREADS, both)]
        conn.execute(_DELETE_QUESTIONS, (user_id, user_id, user_id))
        conn.execute(_DELETE_EVIDENCE, both)
        conn.execute(_DELETE_REVIEW_SCOPES, both)
        conn.execute(_DELETE_REVIEWS, both)
        conn.execute(_DELETE_SUGGESTION_ITEMS, both)
        conn.execute(_DELETE_SUGGESTION_LISTS, both)
        conn.execute(_DELETE_MEAL_PLAN_ITEMS, both)
        conn.execute(_DELETE_MEAL_PLANS, both)
        conn.execute(_DELETE_RATINGS, both)
        conn.execute(_DELETE_RECIPE_INGREDIENTS, one)
        conn.execute(_DELETE_RECIPE_VERSIONS, one)
        conn.execute(_DELETE_RECIPES, one)
        conn.execute(_DELETE_AUDIT, both)
        conn.execute(_DELETE_MESSAGE_DRAFTS, (user_id, user_id, user_id))
        conn.execute(_DELETE_MESSAGES, (user_id, user_id, user_id))
        conn.execute(_DELETE_AI_CONSENTS, (user_id, user_id, user_id))
        conn.execute(_DELETE_CONSENTS, both)
        conn.execute(_DELETE_RELATIONSHIPS, both)
        conn.execute(_DELETE_INVITATIONS, one)
        conn.execute(_DELETE_ATTEMPTS, one)
        conn.execute(_DELETE_SETS, one)
        conn.execute(_DELETE_SESSIONS, one)
        conn.execute(_DELETE_MEALS, one)
        conn.execute(_DELETE_TARGETS, one)
        conn.execute(_DELETE_WEIGHTS, one)
        conn.execute(_DELETE_PROFILES, one)
        conn.execute(_DELETE_PREFERENCES, one)
        conn.execute(_DELETE_READ_MARKS, one)
        conn.execute(_DELETE_USER, one)
        delete_threads(threads)
    # After the commit: the deleted rows' earlier copies leave the write-ahead log too.
    checkpoint(conn)
