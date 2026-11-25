"""The gymer's Art. 9 consents, one per purpose, with the text's version (T11.5, D25).

Consent (b) has a switch per use (T11.6a): each use is a row of its own with its own version.
"""

import pytest

from src.store import ai_consents, users
from src.store.access import NotFound
from tests import store_world as world

VERSION = "0123456789ab"
CHANGED = "ba9876543210"
OWN = ("message_drafts", "media", "dish_suggestions")  # (a), (c), (d): not given to one coach


@pytest.fixture
def conn(store_conn):
    """Build the store world: coaches A and B, a shared, an unshared, an ended and B's client."""
    world.build(store_conn)
    return store_conn


def _thread(conn, gymer):
    """Return the ID of the gymer's (newest) relationship."""
    row = conn.execute(
        "SELECT id FROM coach_clients WHERE client_id = ? ORDER BY id DESC", (gymer,)
    ).fetchone()
    return row[0]


def _target(conn, purpose):
    """Return the relationship argument a purpose takes for the shared gymer."""
    return _thread(conn, world.SHARED) if purpose in ai_consents.PER_RELATIONSHIP else None


def _use(purpose):
    """Return the use a purpose's calls name: `chat` for consent (b), else none."""
    return "chat" if purpose == ai_consents.WITH_USES else None


@pytest.mark.parametrize("purpose", ai_consents.PURPOSES)
def test_a_given_consent_holds_for_its_text_version_only(conn, purpose):
    """A consent holds for the version agreed to; a changed text counts as none until given."""
    target, use = _target(conn, purpose), _use(purpose)
    assert not ai_consents.is_given(conn, world.SHARED, purpose, VERSION, target, use)
    ai_consents.give(conn, world.SHARED, purpose, VERSION, target, use)
    assert ai_consents.is_given(conn, world.SHARED, purpose, VERSION, target, use)
    found = ai_consents.current(conn, world.SHARED, purpose, target, use)
    assert found["text_version"] == VERSION
    assert found["use"] == use
    assert not ai_consents.is_given(conn, world.SHARED, purpose, CHANGED, target, use)
    ai_consents.give(conn, world.SHARED, purpose, CHANGED, target, use)
    assert ai_consents.is_given(conn, world.SHARED, purpose, CHANGED, target, use)
    assert not ai_consents.is_given(conn, world.SHARED, purpose, VERSION, target, use)
    rows = conn.execute(
        "SELECT text_version, withdrawn_at FROM ai_consents WHERE purpose = ? ORDER BY id",
        (purpose,),
    ).fetchall()
    assert [(row[0], row[1] is None) for row in rows] == [(VERSION, False), (CHANGED, True)]


@pytest.mark.parametrize("purpose", ai_consents.PURPOSES)
def test_a_withdrawn_consent_is_refused_and_can_be_given_again(conn, purpose):
    """Withdrawing ends the consent at once; giving it again is a new row."""
    target, use = _target(conn, purpose), _use(purpose)
    first = ai_consents.give(conn, world.SHARED, purpose, VERSION, target, use)
    assert ai_consents.give(conn, world.SHARED, purpose, VERSION, target, use) == first  # kept
    assert ai_consents.withdraw(conn, world.SHARED, purpose, target, use)
    assert not ai_consents.is_given(conn, world.SHARED, purpose, VERSION, target, use)
    assert ai_consents.current(conn, world.SHARED, purpose, target, use) is None
    assert not ai_consents.withdraw(conn, world.SHARED, purpose, target, use)  # none open
    assert ai_consents.give(conn, world.SHARED, purpose, VERSION, target, use) != first
    assert ai_consents.is_given(conn, world.SHARED, purpose, VERSION, target, use)


@pytest.mark.parametrize("purpose", ai_consents.PURPOSES)
def test_another_purposes_consent_does_not_count(conn, purpose):
    """Every other purpose given leaves this one missing."""
    for other in ai_consents.PURPOSES:
        if other != purpose:
            ai_consents.give(conn, world.SHARED, other, VERSION, _target(conn, other), _use(other))
    assert not ai_consents.is_given(
        conn, world.SHARED, purpose, VERSION, _target(conn, purpose), _use(purpose)
    )


@pytest.mark.parametrize("purpose", ai_consents.PER_RELATIONSHIP)
def test_a_consent_to_one_coach_counts_as_missing_once_the_relationship_ended(conn, purpose):
    """(b) and (e) belong to one relationship: after its end they are none, and none is given."""
    thread, use = _thread(conn, world.SHARED), _use(purpose)
    ai_consents.give(conn, world.SHARED, purpose, VERSION, thread, use)
    users.end_relationship(conn, world.SHARED, thread)
    assert not ai_consents.is_given(conn, world.SHARED, purpose, VERSION, thread, use)
    with pytest.raises(NotFound):
        ai_consents.give(conn, world.SHARED, purpose, VERSION, thread, use)
    ended = _thread(conn, world.ENDED)
    with pytest.raises(NotFound):
        ai_consents.give(conn, world.ENDED, purpose, VERSION, ended, use)


@pytest.mark.parametrize("purpose", ai_consents.PER_RELATIONSHIP)
def test_a_consent_to_one_coach_does_not_count_for_another_relationship(conn, purpose):
    """A (b) for one relationship is no consent for another, nor without one."""
    thread, use = _thread(conn, world.SHARED), _use(purpose)
    ai_consents.give(conn, world.SHARED, purpose, VERSION, thread, use)
    assert not ai_consents.is_given(conn, world.SHARED, purpose, VERSION, None, use)
    assert not ai_consents.is_given(conn, world.SHARED, purpose, VERSION, thread + 1000, use)


@pytest.mark.parametrize("use", ai_consents.USES)
def test_each_use_of_b_is_on_alone_and_off_alone(conn, use):
    """One use switched on leaves the others off; switched off, it leaves the others on."""
    thread = _thread(conn, world.SHARED)
    ai_consents.give(conn, world.SHARED, "coach_thread", VERSION, thread, use)
    for other in ai_consents.USES:
        on = ai_consents.is_given(conn, world.SHARED, "coach_thread", VERSION, thread, other)
        assert on is (other == use)
    for other in ai_consents.USES:
        ai_consents.give(conn, world.SHARED, "coach_thread", VERSION, thread, other)
    assert ai_consents.withdraw(conn, world.SHARED, "coach_thread", thread, use)
    for other in ai_consents.USES:
        on = ai_consents.is_given(conn, world.SHARED, "coach_thread", VERSION, thread, other)
        assert on is (other != use)


def test_a_new_use_starts_off_and_keeps_the_uses_already_set(conn):
    """A use a later ticket adds, with a new text, starts off; `chat` keeps working as set."""
    thread = _thread(conn, world.SHARED)
    ai_consents.give(conn, world.SHARED, "coach_thread", VERSION, thread, "chat")
    # The new use's text has a version of its own; the chat use's text is unchanged.
    assert not ai_consents.is_given(conn, world.SHARED, "coach_thread", CHANGED, thread, "review")
    ai_consents.give(conn, world.SHARED, "coach_thread", CHANGED, thread, "review")
    assert ai_consents.is_given(conn, world.SHARED, "coach_thread", VERSION, thread, "chat")
    assert ai_consents.is_given(conn, world.SHARED, "coach_thread", CHANGED, thread, "review")
    rows = conn.execute(
        "SELECT use, text_version FROM ai_consents WHERE withdrawn_at IS NULL ORDER BY id"
    ).fetchall()
    assert [tuple(row) for row in rows] == [("chat", VERSION), ("review", CHANGED)]


@pytest.mark.parametrize(
    ("user", "purpose", "relationship", "use"),
    [
        (world.COACH_A, "message_drafts", None, None),  # a coach gives no consent
        (world.MISSING, "message_drafts", None, None),
        ("", "message_drafts", None, None),
        (world.SHARED, "sharing", None, None),  # not a purpose
        (world.SHARED, "message_drafts", "shared", None),  # (a) names no relationship
        (world.SHARED, "message_drafts", None, "chat"),  # (a) has no use
        (world.SHARED, "client_notes", "shared", "chat"),  # (e) has no use
        (world.SHARED, "coach_thread", None, "chat"),  # (b) needs a relationship
        (world.SHARED, "coach_thread", "shared", None),  # (b) needs a use
        (world.SHARED, "coach_thread", "shared", "summary"),  # not a use
        (world.SHARED, "coach_thread", "shared", 1),
        (world.SHARED, "coach_thread", "others", "chat"),  # another gymer's relationship
        (world.SHARED, "coach_thread", "x", "chat"),
    ],
)
def test_a_consent_for_a_wrong_target_is_not_found_and_writes_nothing(
    conn, user, purpose, relationship, use
):
    """Every bad target is the same NotFound, writes nothing and reads as no consent."""
    target = {
        "shared": _thread(conn, world.SHARED),
        "others": _thread(conn, world.OTHERS),
    }.get(relationship, relationship)
    for call in (ai_consents.give, ai_consents.withdraw, ai_consents.current):
        args = (VERSION,) if call is ai_consents.give else ()
        with pytest.raises(NotFound):
            call(conn, user, purpose, *args, target, use)
    assert not ai_consents.is_given(conn, user, purpose, VERSION, target, use)
    assert conn.execute("SELECT count(*) FROM ai_consents").fetchone()[0] == 0


@pytest.mark.parametrize("version", ["", "0123456789AB", "0123", None, 12])
def test_a_malformed_version_is_refused_and_never_given(conn, version):
    """A version that is not 12 lowercase hex characters writes nothing and is never given."""
    with pytest.raises(ValueError):
        ai_consents.give(conn, world.SHARED, "message_drafts", version)
    assert not ai_consents.is_given(conn, world.SHARED, "message_drafts", version)


def test_the_table_refuses_a_b_row_without_a_use_and_a_use_on_another_purpose(conn):
    """The schema itself keeps `use` to (b), and requires it there."""
    import sqlite3

    thread = _thread(conn, world.SHARED)
    insert = (
        "INSERT INTO ai_consents (user_id, purpose, relationship_id, use, text_version, given_at)"
        " VALUES (?, ?, ?, ?, ?, '2026-11-25T10:00:00+00:00')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(insert, (world.SHARED, "coach_thread", thread, None, VERSION))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(insert, (world.SHARED, "message_drafts", None, "chat", VERSION))
