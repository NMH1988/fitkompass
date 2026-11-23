"""UI tests for the Messages page (T11.4b, PRD feature 30, AC-45).

The thread is drawn by a browser component; AppTest runs no JavaScript, so these tests read what the
page hands the component (its `data`, a JSON text in the element) and its fixed key. The socket's
JavaScript is tested with Node (tests/js/messages.test.mjs, tests/test_messages_component.py), and
the socket itself on a real Streamlit server (tests/test_realtime_server.py).
"""

import json

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest
from streamlit.util import calc_hash

from src import chat, config
from src.realtime import page as realtime_page
from src.realtime import server as realtime_server
from src.realtime import tokens
from src.store import db, messages, users
from tests.fakes import patch_config
from tests.test_app_account import (
    APP,
    AUTH,
    PROFILE,
    SECRET,
    USER_ID,
    FakeUser,
    signed_in,
    store_account,
    texts,
)
from views import messages as messages_view
from views import navigation

pytestmark = pytest.mark.usefixtures("no_env_key")

CHAT_SECRET = "test-chat-secret-" + "m" * 32
GYMER = "gym-mia"
COACH = "coach-ola"


def _run(monkeypatch, *, language: str = "en", chat_secret: bool = True) -> AppTest:
    """Run app.py signed in as USER_ID, open the Messages page and return the handle."""
    monkeypatch.setattr(st, "user", signed_in())
    at = AppTest.from_file(str(APP))
    at.secrets["auth"] = dict(AUTH)
    at.secrets["account"] = {"user_key_secret": SECRET}
    if chat_secret:
        at.secrets["chat"] = {"token_secret": CHAT_SECRET}
    at.session_state["language"] = language
    at.run(timeout=30)
    at._page_hash = calc_hash(messages_view.URL_PATH)
    return at.run(timeout=30)


@pytest.fixture
def mounted(monkeypatch):
    """Run as under `streamlit run serve.py`: the chat socket is mounted in this process."""
    monkeypatch.setitem(realtime_server._MOUNTED, "chat", True)


def _user(user_id: str, role: str, name: str) -> None:
    """Store a made-up user."""
    with db.connect() as conn:
        users.create_user(conn, user_id, role, name)


def _pair(coach: str, client: str, texts_by_sender: tuple[tuple[str, str], ...] = ()) -> int:
    """Pair a coach and a gymer and store their messages; return the thread's ID."""
    with db.connect() as conn:
        thread = users.start_relationship(conn, coach, client)
        for sender, text in texts_by_sender:
            messages.send_message(conn, sender, thread, text)
    return thread


def _end(actor: str, thread: int) -> None:
    """End a relationship."""
    with db.connect() as conn:
        users.end_relationship(conn, actor, thread)


def _component(at: AppTest):
    """Return the one Messages component of the run."""
    [element] = at.get("bidi_component")
    return element.proto


def _data(at: AppTest) -> dict:
    """Return the data the page handed the component."""
    return json.loads(_component(at).json)


def _coach_with_client() -> int:
    """Store USER_ID as a coach with one client and a two-message thread; return the thread."""
    store_account("coach", "Coach Sam")
    _user(GYMER, "gymer", "Mia")
    return _pair(USER_ID, GYMER, ((GYMER, "Leg day done"), (USER_ID, "Well done, Mia")))


def test_both_roles_have_the_messages_page():
    """A coach and a gymer each have Messages; a guest and a new account do not."""
    assert navigation.MESSAGES in navigation.PAGES_BY_ROLE["coach"]
    assert navigation.MESSAGES in navigation.PAGES_BY_ROLE["gymer"]
    for role in (None, navigation.START, navigation.PENDING):
        assert navigation.MESSAGES not in navigation.PAGES_BY_ROLE[role]


def test_without_the_socket_the_thread_is_read_only_and_the_page_says_so(monkeypatch):
    """`streamlit run app.py`: the stored thread, no token or send box, a note on how to start."""
    _coach_with_client()
    at = _run(monkeypatch)
    data = _data(at)
    assert [(item["text"], item["mine"]) for item in data["messages"]] == [
        ("Leg day done", False),
        ("Well done, Mia", True),
    ]
    assert data["socket"] is None and data["can_send"] is False
    assert "streamlit run serve.py" in texts(at)
    assert "Conversation with Mia" in texts(at)


def test_with_the_socket_the_page_mints_a_token_for_the_acting_user(monkeypatch, mounted):
    """The token in the data verifies to the signed-in user and the thread, and nothing else."""
    thread = _coach_with_client()
    at = _run(monkeypatch)
    data = _data(at)
    claims = tokens.verify(data["socket"]["token"], CHAT_SECRET)
    assert (claims.user_id, claims.thread_id) == (USER_ID, thread)
    assert data["socket"]["path"] == config.CHAT_MOUNT_PATH + config.CHAT_SOCKET_PATH
    assert data["socket"]["expires_in"] == config.CHAT_TOKEN_TTL_SECONDS
    assert data["socket"]["renew_before"] == config.CHAT_TOKEN_RENEW_BEFORE_SECONDS
    assert data["socket"]["renew_retry"] == config.CHAT_RENEW_RETRY_SECONDS
    assert data["can_send"] is True and data["max_chars"] == config.MESSAGE_MAX_CHARS
    assert "streamlit run serve.py" not in texts(at)


def test_without_a_secret_the_socket_is_off_even_when_mounted(monkeypatch, mounted):
    """No token secret: no token is minted, and the page says real-time messages are off."""
    _coach_with_client()
    at = _run(monkeypatch, chat_secret=False)
    assert _data(at)["socket"] is None and "streamlit run serve.py" in texts(at)


def test_a_rerun_gives_a_new_token_to_the_same_component(monkeypatch, mounted):
    """A later run mints a new token; the component's key, and so its element, stay the same."""
    thread = _coach_with_client()
    # Each run mints a minute later than the one before (the token's expiry is in whole seconds).
    clock = iter(range(1_800_000_000, 1_800_100_000, 60))
    real = realtime_page.socket_data
    monkeypatch.setattr(
        realtime_page, "socket_data", lambda user, thread: real(user, thread, now=next(clock))
    )
    at = _run(monkeypatch)
    first_id, first = _component(at).id, _data(at)["socket"]["token"]
    at.run(timeout=30)
    assert _component(at).id == first_id and messages_view.component_key(thread) in first_id
    assert _data(at)["socket"]["token"] != first


def test_the_token_stays_out_of_the_session_and_the_url(monkeypatch, mounted):
    """The token is only in the component's data: not in session state or query parameters."""
    _coach_with_client()
    at = _run(monkeypatch)
    token = _data(at)["socket"]["token"]
    assert token not in repr(at.session_state.to_dict())
    assert token not in repr(dict(at.query_params))


def test_after_the_end_both_sides_read_and_neither_can_send(monkeypatch, mounted):
    """An ended relationship: the coach and the gymer read the thread, with no token or send box."""
    thread = _coach_with_client()
    _end(USER_ID, thread)
    at = _run(monkeypatch)
    data = _data(at)
    assert len(data["messages"]) == 2 and data["socket"] is None and data["can_send"] is False
    assert any("neither of you can send" in str(box.value) for box in at.info)

    # The same from the gymer's side, the coach being the other one now.
    with db.connect() as conn:
        conn.execute("DELETE FROM messages")
        conn.execute("DELETE FROM coach_clients")
        conn.execute("DELETE FROM users")
    store_account("gymer", profile=PROFILE)
    _user(COACH, "coach", "Coach Ola")
    other = _pair(COACH, USER_ID, ((COACH, "How was the run?"),))
    _end(USER_ID, other)
    at = _run(monkeypatch)
    data = _data(at)
    assert [item["text"] for item in data["messages"]] == ["How was the run?"]
    assert data["socket"] is None and data["can_send"] is False
    assert data["other_name"] == "Coach Ola"


def test_a_gymer_with_an_active_coach_can_send(monkeypatch, mounted):
    """The gymer's side of an active relationship gets its own token and the send box."""
    store_account("gymer", profile=PROFILE)
    _user(COACH, "coach", "Coach Ola")
    thread = _pair(COACH, USER_ID)
    at = _run(monkeypatch)
    data = _data(at)
    claims = tokens.verify(data["socket"]["token"], CHAT_SECRET)
    assert (claims.user_id, claims.thread_id) == (USER_ID, thread)
    assert data["messages"] == [] and data["can_send"] is True


def test_a_page_at_another_address_gets_no_token(monkeypatch, mounted):
    """A page the socket's origin check would refuse is told where to open the app instead."""
    _coach_with_client()
    monkeypatch.setattr(realtime_page, "page_may_connect", lambda url, port: False)
    at = _run(monkeypatch)
    assert _data(at)["socket"] is None
    assert "only when the app is opened at http://localhost:8501" in texts(at)


def test_a_coach_picks_among_threads_with_an_ended_one_marked(monkeypatch):
    """Two clients, one former: the picker lists both, the active one first and preselected."""
    _coach_with_client()
    _user("gym-noa", "gymer", "Noa")
    former = _pair(USER_ID, "gym-noa", (("gym-noa", "Thanks for everything"),))
    _end(USER_ID, former)
    at = _run(monkeypatch)
    [picker] = at.selectbox
    assert picker.options == ["Mia", "Noa (ended)"] and picker.value != former
    picker.set_value(former).run(timeout=30)
    assert [item["text"] for item in _data(at)["messages"]] == ["Thanks for everything"]


@pytest.mark.parametrize(
    ("role", "expected"),
    [("gymer", "connect with a coach on Coach and sharing"), ("coach", "a client connects")],
)
def test_with_no_relationship_the_page_says_how_one_starts(monkeypatch, role, expected):
    """No coach or no client yet: no component, a note on how a conversation starts."""
    store_account(role, profile=PROFILE if role == "gymer" else None)
    at = _run(monkeypatch)
    assert at.get("bidi_component") == [] and expected in texts(at)


@pytest.mark.parametrize(
    ("language", "stored", "made_up", "send"),
    [
        ("en", "stored in this app's data file", "Use made-up data only", "Send"),
        ("de", "Datendatei dieser App", "nur erfundene Daten", "Senden"),
    ],
)
def test_the_page_says_what_is_stored_in_both_languages(
    monkeypatch, mounted, language, stored, made_up, send
):
    """The intro (stored, read after the end, deleted by either side) and the component's texts."""
    _coach_with_client()
    at = _run(monkeypatch, language=language)
    page = texts(at)
    assert stored in page and made_up in page
    data = _data(at)
    assert data["labels"]["send"] == send and data["locale"] == language


def test_the_component_s_code_comes_from_the_repo():
    """The component's JavaScript and CSS are the repo's files, not text from anywhere else."""
    folder = messages_view._HERE
    assert folder.name == "components" and (folder / "messages.mjs").is_file()
    assert "export default function" in (folder / "messages.mjs").read_text(encoding="utf-8")


def test_a_guest_never_reaches_the_page(monkeypatch):
    """With no account the Messages URL shows the start page, not a thread."""
    monkeypatch.setattr(st, "user", FakeUser())
    at = AppTest.from_file(str(APP))
    at.secrets["auth"] = dict(AUTH)
    at.secrets["account"] = {"user_key_secret": SECRET}
    at.run(timeout=30)
    at._page_hash = calc_hash(messages_view.URL_PATH)
    at.run(timeout=30)
    assert at.get("bidi_component") == [] and "Sign in to continue" in texts(at)


def _fragment_alone(user_id: str, thread_id: int) -> None:
    """Run the thread's fragment by itself, as a renewal's rerun does."""
    from views import messages as view

    view._thread(user_id, thread_id)


def test_a_renewal_after_the_other_side_ended_it_gets_no_token(monkeypatch, mounted):
    """The fragment reads the relationship itself: ended since the page ran, it turns read-only."""
    patch_config(monkeypatch, "chat_token_secret", lambda: CHAT_SECRET)
    thread = _coach_with_client()
    at = AppTest.from_function(_fragment_alone, args=(USER_ID, thread))
    at.session_state["language"] = "en"
    at.run(timeout=30)
    assert _data(at)["socket"] is not None  # active: a token
    _end(GYMER, thread)  # the other side ends it while the page is open
    at.run(timeout=30)
    data = _data(at)
    assert data["socket"] is None and data["can_send"] is False and len(data["messages"]) == 2
    assert any("neither of you can send" in str(box.value) for box in at.info)


def test_the_name_in_the_heading_is_shown_as_text(monkeypatch):
    """A display name with Markdown characters is escaped in the conversation's heading."""
    store_account("coach", "Coach Sam")
    _user(GYMER, "gymer", "Mia _big_")
    _pair(USER_ID, GYMER)
    at = _run(monkeypatch)
    escaped = chat.escape_markdown("Mia _big_")
    assert escaped != "Mia _big_"
    assert any(escaped in str(item.value) for item in at.markdown)
