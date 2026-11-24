"""The gymer's Art. 9 consents, one per purpose, with the text's version (T11.5, D25)."""

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


@pytest.mark.parametrize("purpose", ai_consents.PURPOSES)
def test_a_given_consent_holds_for_its_text_version_only(conn, purpose):
    """A consent holds for the version agreed to; a changed text counts as none until given."""
    target = _target(conn, purpose)
    assert not ai_consents.is_given(conn, world.SHARED, purpose, VERSION, target)
    ai_consents.give(conn, world.SHARED, purpose, VERSION, target)
    assert ai_consents.is_given(conn, world.SHARED, purpose, VERSION, target)
    assert ai_consents.current(conn, world.SHARED, purpose, target)["text_version"] == VERSION
    assert not ai_consents.is_given(conn, world.SHARED, purpose, CHANGED, target)
    ai_consents.give(conn, world.SHARED, purpose, CHANGED, target)
    assert ai_consents.is_given(conn, world.SHARED, purpose, CHANGED, target)
    assert not ai_consents.is_given(conn, world.SHARED, purpose, VERSION, target)
    rows = conn.execute(
        "SELECT text_version, withdrawn_at FROM ai_consents WHERE purpose = ? ORDER BY id",
        (purpose,),
    ).fetchall()
    assert [(row[0], row[1] is None) for row in rows] == [(VERSION, False), (CHANGED, True)]


@pytest.mark.parametrize("purpose", ai_consents.PURPOSES)
def test_a_withdrawn_consent_is_refused_and_can_be_given_again(conn, purpose):
    """Withdrawing ends the consent at once; giving it again is a new row."""
    target = _target(conn, purpose)
    first = ai_consents.give(conn, world.SHARED, purpose, VERSION, target)
    assert ai_consents.give(conn, world.SHARED, purpose, VERSION, target) == first  # kept
    assert ai_consents.withdraw(conn, world.SHARED, purpose, target)
    assert not ai_consents.is_given(conn, world.SHARED, purpose, VERSION, target)
    assert ai_consents.current(conn, world.SHARED, purpose, target) is None
    assert not ai_consents.withdraw(conn, world.SHARED, purpose, target)  # none open
    assert ai_consents.give(conn, world.SHARED, purpose, VERSION, target) != first
    assert ai_consents.is_given(conn, world.SHARED, purpose, VERSION, target)


@pytest.mark.parametrize("purpose", ai_consents.PURPOSES)
def test_another_purposes_consent_does_not_count(conn, purpose):
    """Every other purpose given leaves this one missing."""
    for other in ai_consents.PURPOSES:
        if other != purpose:
            ai_consents.give(conn, world.SHARED, other, VERSION, _target(conn, other))
    assert not ai_consents.is_given(conn, world.SHARED, purpose, VERSION, _target(conn, purpose))


@pytest.mark.parametrize("purpose", ai_consents.PER_RELATIONSHIP)
def test_a_consent_to_one_coach_counts_as_missing_once_the_relationship_ended(conn, purpose):
    """(b) and (e) belong to one relationship: after its end they are none, and none is given."""
    thread = _thread(conn, world.SHARED)
    ai_consents.give(conn, world.SHARED, purpose, VERSION, thread)
    users.end_relationship(conn, world.SHARED, thread)
    assert not ai_consents.is_given(conn, world.SHARED, purpose, VERSION, thread)
    with pytest.raises(NotFound):
        ai_consents.give(conn, world.SHARED, purpose, VERSION, thread)
    ended = _thread(conn, world.ENDED)
    with pytest.raises(NotFound):
        ai_consents.give(conn, world.ENDED, purpose, VERSION, ended)


@pytest.mark.parametrize("purpose", ai_consents.PER_RELATIONSHIP)
def test_a_consent_to_one_coach_does_not_count_for_another_relationship(conn, purpose):
    """A (b) for one relationship is no consent for another, nor without one."""
    thread = _thread(conn, world.SHARED)
    ai_consents.give(conn, world.SHARED, purpose, VERSION, thread)
    assert not ai_consents.is_given(conn, world.SHARED, purpose, VERSION, None)
    assert not ai_consents.is_given(conn, world.SHARED, purpose, VERSION, thread + 1000)


@pytest.mark.parametrize(
    ("user", "purpose", "relationship"),
    [
        (world.COACH_A, "message_drafts", None),  # a coach gives no consent
        (world.MISSING, "message_drafts", None),
        ("", "message_drafts", None),
        (world.SHARED, "sharing", None),  # not a purpose
        (world.SHARED, "message_drafts", "shared"),  # (a) names no relationship
        (world.SHARED, "coach_thread", None),  # (b) needs one
        (world.SHARED, "coach_thread", "others"),  # another gymer's relationship
        (world.SHARED, "coach_thread", "x"),
    ],
)
def test_a_consent_for_a_wrong_target_is_not_found_and_writes_nothing(
    conn, user, purpose, relationship
):
    """Every bad target is the same NotFound, writes nothing and reads as no consent."""
    target = {
        "shared": _thread(conn, world.SHARED),
        "others": _thread(conn, world.OTHERS),
    }.get(relationship, relationship)
    for call in (ai_consents.give, ai_consents.withdraw, ai_consents.current):
        args = (VERSION,) if call is ai_consents.give else ()
        with pytest.raises(NotFound):
            call(conn, user, purpose, *args, target)
    assert not ai_consents.is_given(conn, user, purpose, VERSION, target)
    assert conn.execute("SELECT count(*) FROM ai_consents").fetchone()[0] == 0


@pytest.mark.parametrize("version", ["", "0123456789AB", "0123", None, 12])
def test_a_malformed_version_is_refused_and_never_given(conn, version):
    """A version that is not 12 lowercase hex characters writes nothing and is never given."""
    with pytest.raises(ValueError):
        ai_consents.give(conn, world.SHARED, "message_drafts", version)
    assert not ai_consents.is_given(conn, world.SHARED, "message_drafts", version)
