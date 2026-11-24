"""Tests for the chat socket's app (T11.4a, D24): delivery, catch-up, refusals and renewal.

FastAPI's TestClient runs the app in one event loop of its own, so two connections from one client
share the server's hub, as two browsers on one uvicorn process do. The store is the test's own
temporary file (conftest), with the made-up world of tests/store_world.py.
"""

import io
import json
import sqlite3
import threading
import time
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src import config, observability
from src.realtime import app as chat_app
from src.realtime import tokens
from src.store import db, messages, my_data, users
from src.store.access import NotFound
from tests import store_world as world
from tests.fakes import patch_config

SECRET = "test-chat-secret-" + "x" * 32
ORIGIN = "http://localhost:8501"
PATH = config.CHAT_SOCKET_PATH
CANARY = "CANARY-chat-text-5bd1"


@pytest.fixture
def relationships(store_conn):
    """Build the made-up world in the test's store; return its relationship IDs by gymer."""
    return world.build(store_conn)


@pytest.fixture
def secret(monkeypatch):
    """Give the server a test secret through the one config function."""
    patch_config(monkeypatch, "chat_token_secret", lambda: SECRET)
    return SECRET


@pytest.fixture
def log_stream():
    """Send the app's JSON log lines to a buffer the test reads."""
    stream = io.StringIO()
    observability.configure_logging(stream=stream)
    return stream


def _chat_app():
    """Return the chat app on the test's store file, allowing the local page's origin."""
    return chat_app.create_app(lambda: config.STORE_PATH, lambda: frozenset({ORIGIN}))


@pytest.fixture
def client(relationships, secret, log_stream):
    """Yield a TestClient on a chat app that uses the test's store file."""
    with TestClient(_chat_app()) as test_client:
        yield test_client


def _token(user: str, thread: int, **kwargs) -> str:
    """Return a token minted with the test secret."""
    return tokens.mint(user, thread, SECRET, **kwargs)


def _forged(token: str) -> str:
    """Return the token with one signature character changed, so it never verifies."""
    # The second-to-last character holds only signature bits (the last also holds padding bits the
    # decoder ignores), and it always changes: a fixed "AA" ending left a token that already ended
    # in "AA" valid, about once in 4096 runs.
    return token[:-2] + ("B" if token[-2] == "A" else "A") + token[-1]


def _auth(token: object, after_id: object = 0) -> dict:
    """Return an auth frame."""
    return {"type": "auth", "token": token, "after_id": after_id}


def _until_ready(socket) -> list[dict]:
    """Return the message items received before the next ready frame."""
    items = []
    while True:
        frame = socket.receive_json()
        if frame["type"] == "ready":
            return items
        assert frame["type"] == "messages", frame
        items.extend(frame["items"])


@contextmanager
def _open(client, user, thread, *, after_id=0, origin=ORIGIN):
    """Open a socket, send its token and yield (socket, the catch-up's items)."""
    with client.websocket_connect(PATH, headers={"origin": origin}) as socket:
        socket.send_json(_auth(_token(user, thread), after_id))
        yield socket, _until_ready(socket)


def _send(store_conn, sender, thread, text) -> int:
    """Store a message directly; return its ID."""
    return messages.send_message(store_conn, sender, thread, text)


def _closed_with(socket) -> int:
    """Return the close code the server sent next (fails if a data frame comes first)."""
    with pytest.raises(WebSocketDisconnect) as closed:
        socket.receive_json()
    return closed.value.code


def _probe(socket, user, thread, after_id) -> list[dict]:
    """Renew the token and return what arrives before ready: proves nothing came in between."""
    socket.send_json(_auth(_token(user, thread), after_id))
    return _until_ready(socket)


# --- Delivery ------------------------------------------------------------------------------------


def test_a_message_reaches_the_other_side_s_open_socket_and_is_stored(
    client, relationships, store_conn
):
    """The gymer sends; the coach's socket gets it as not theirs, the gymer's as theirs."""
    thread = relationships[world.SHARED]
    with (
        _open(client, world.COACH_A, thread) as (coach, _),
        _open(client, world.SHARED, thread) as (gymer, _),
    ):
        gymer.send_json({"type": "send", "text": "Had oats and two eggs"})
        to_coach = coach.receive_json()
        to_gymer = gymer.receive_json()
    assert to_coach["type"] == "messages" and to_coach["more"] is False
    [item] = to_coach["items"]
    assert item["text"] == "Had oats and two eggs" and item["mine"] is False
    assert set(item) == {"id", "mine", "text", "created_at"}  # no user ID reaches the browser
    assert to_gymer["items"][0]["mine"] is True
    stored = messages.list_messages(store_conn, world.COACH_A, thread)
    assert [(m["sender_id"], m["text"]) for m in stored] == [(world.SHARED, item["text"])]


def test_the_sender_is_always_the_token_s_user(client, relationships, store_conn):
    """A frame cannot name another sender: the extra field is refused, nothing is stored."""
    thread = relationships[world.SHARED]
    with _open(client, world.SHARED, thread) as (gymer, _):
        gymer.send_json({"type": "send", "text": "x", "sender_id": world.COACH_A})
        assert _closed_with(gymer) == config.CHAT_CLOSE_REFUSED
    assert messages.list_messages(store_conn, world.COACH_A, thread) == []


def test_a_token_minted_for_one_user_cannot_act_as_another(client, relationships, store_conn):
    """The gymer's token sends as the gymer, even on the coach's thread with the coach's socket."""
    thread = relationships[world.SHARED]
    with _open(client, world.SHARED, thread) as (gymer, _):
        gymer.send_json({"type": "send", "text": "From the gymer"})
        gymer.receive_json()
    [stored] = messages.list_messages(store_conn, world.COACH_A, thread)
    assert stored["sender_id"] == world.SHARED


# --- Catch-up ------------------------------------------------------------------------------------


def test_the_first_token_catches_up_the_messages_after_the_page_s_last(
    client, relationships, store_conn
):
    """With after_id, only the later messages of the token's own thread are sent, oldest first."""
    thread = relationships[world.SHARED]
    ids = [_send(store_conn, world.SHARED, thread, f"m{n}") for n in range(3)]
    _send(store_conn, world.UNSHARED, relationships[world.UNSHARED], "another thread")
    with _open(client, world.COACH_A, thread, after_id=ids[0]) as (_, items):
        assert [item["id"] for item in items] == ids[1:]


@pytest.mark.parametrize("after_id", [10**9, 0])
def test_a_made_up_after_id_returns_nothing_extra(client, relationships, store_conn, after_id):
    """Any ID gives only this thread's later messages: none past the end, never another thread's."""
    other = relationships[world.UNSHARED]
    _send(store_conn, world.UNSHARED, other, "another thread's message")
    with _open(client, world.COACH_A, relationships[world.SHARED], after_id=after_id) as (_, items):
        assert items == []


def test_the_catch_up_sends_at_most_the_configured_number_and_says_more(
    client, relationships, store_conn, monkeypatch
):
    """At most CHAT_CATCH_UP_LIMIT at once, with more=True when later messages are left."""
    monkeypatch.setattr(config, "CHAT_CATCH_UP_LIMIT", 2)
    thread = relationships[world.SHARED]
    ids = [_send(store_conn, world.SHARED, thread, f"m{n}") for n in range(5)]
    with client.websocket_connect(PATH, headers={"origin": ORIGIN}) as socket:
        socket.send_json(_auth(_token(world.COACH_A, thread)))
        frame = socket.receive_json()
        assert [item["id"] for item in frame["items"]] == ids[:2] and frame["more"] is True
        assert socket.receive_json() == {"type": "ready"}
        # The page asks for the rest with its new last ID.
        assert [i["id"] for i in _probe(socket, world.COACH_A, thread, ids[1])] == ids[2:4]


def test_the_ended_relationship_s_thread_is_still_read(client, relationships, store_conn):
    """After the end both sides read the thread (T11.3), so the socket opens and catches up."""
    thread = relationships[world.ENDED]
    with _open(client, world.ENDED, thread) as (gymer, items):
        assert items == []
        gymer.send_json({"type": "send", "text": "Too late"})
        assert gymer.receive_json() == {"type": "error", "code": config.CHAT_ERROR_NOT_SENT}


# --- Refusals before any message is read ---------------------------------------------------------


def _refused_frames(relationships) -> dict[str, object]:
    """Return the first frames that must be refused, by name."""
    thread = relationships[world.SHARED]
    good = _token(world.COACH_A, thread)
    other_secret = tokens.mint(world.COACH_A, thread, "test-other-secret-" + "y" * 32)
    return {
        "bad signature": _auth(other_secret),
        "cut signature": _auth(good[:-3]),
        "expired": _auth(_token(world.COACH_A, thread, now=time.time() - 10**4)),
        "another thread": _auth(_token(world.COACH_A, relationships[world.OTHERS])),
        "another user": _auth(_token(world.COACH_B, thread)),
        "a stranger": _auth(_token(world.MISSING, thread)),
        "missing token": {"type": "auth", "after_id": 0},
        "null token": _auth(None),
        "send first": {"type": "send", "text": "hello"},
        "unknown type": {"type": "subscribe", "token": good},
        "extra field": {**_auth(good), "user_id": world.COACH_A},
        "bad after_id": _auth(good, -1),
        "text after_id": _auth(good, "5"),
        "not an object": [good],
        "not json": "token " + good,
        "deep json": "[" * 3000 + "]" * 3000,
        "oversized": {**_auth(good), "pad": "x" * config.CHAT_MAX_FRAME_BYTES},
    }


@pytest.mark.parametrize(
    "case",
    [
        "bad signature",
        "cut signature",
        "expired",
        "another thread",
        "another user",
        "a stranger",
        "missing token",
        "null token",
        "send first",
        "unknown type",
        "extra field",
        "bad after_id",
        "text after_id",
        "not an object",
        "not json",
        "deep json",
        "oversized",
    ],
)
def test_a_bad_first_frame_closes_the_socket_before_any_message(
    client, relationships, store_conn, case
):
    """Every bad first frame closes with the one refusal code; no stored message is sent."""
    _send(store_conn, world.SHARED, relationships[world.SHARED], CANARY)
    frame = _refused_frames(relationships)[case]
    with client.websocket_connect(PATH, headers={"origin": ORIGIN}) as socket:
        if isinstance(frame, str):
            socket.send_text(frame)
        else:
            socket.send_json(frame)
        assert _closed_with(socket) == config.CHAT_CLOSE_REFUSED


def test_a_binary_first_frame_is_refused(client, relationships):
    """A binary frame is not a token."""
    with client.websocket_connect(PATH, headers={"origin": ORIGIN}) as socket:
        socket.send_bytes(b"\x00\x01")
        assert _closed_with(socket) == config.CHAT_CLOSE_REFUSED


def test_no_token_in_time_closes_the_socket(client, monkeypatch):
    """A socket that sends nothing is closed after CHAT_AUTH_WAIT_SECONDS."""
    monkeypatch.setattr(config, "CHAT_AUTH_WAIT_SECONDS", 0.2)
    with client.websocket_connect(PATH, headers={"origin": ORIGIN}) as socket:
        assert _closed_with(socket) == config.CHAT_CLOSE_REFUSED


@pytest.mark.parametrize(
    "path, headers",
    [
        (f"{PATH}?token=abc", {"origin": ORIGIN}),
        (f"{PATH}?x=1", {"origin": ORIGIN}),
        (PATH, {"origin": "http://evil.example"}),
        (PATH, {"origin": "http://localhost:8501.evil.example"}),
        (PATH, {"origin": "null"}),
        (PATH, {}),
    ],
)
def test_a_query_string_or_a_foreign_origin_is_refused_at_the_handshake(
    client, relationships, path, headers
):
    """The handshake itself fails: no socket is opened, no frame is read."""
    with pytest.raises(WebSocketDisconnect) as refused:
        with client.websocket_connect(path, headers=headers):
            pass
    assert refused.value.code == config.CHAT_CLOSE_REFUSED


def test_without_a_secret_every_socket_is_refused(client, relationships, monkeypatch):
    """No secret configured: nothing can verify, so the handshake is refused."""
    patch_config(monkeypatch, "chat_token_secret", lambda: None)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(PATH, headers={"origin": ORIGIN}):
            pass


def test_another_path_has_no_socket(client):
    """Only the one path serves a socket; a thread ID in the path is nothing."""
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"{PATH}/1", headers={"origin": ORIGIN}):
            pass


# --- Renewal and expiry --------------------------------------------------------------------------


def test_a_renewal_keeps_the_socket_past_the_first_token_s_expiry(
    client, relationships, store_conn, monkeypatch
):
    """A new token on the open socket moves its expiry; messages still arrive after the first's."""
    # A token's expiry is in whole seconds, so with 2 seconds the first one lives more than 1.
    monkeypatch.setattr(config, "CHAT_TOKEN_TTL_SECONDS", 2)
    thread = relationships[world.SHARED]
    with _open(client, world.COACH_A, thread) as (coach, _):
        monkeypatch.setattr(config, "CHAT_TOKEN_TTL_SECONDS", 30)
        assert _probe(coach, world.COACH_A, thread, 0) == []
        time.sleep(2.0)  # past the first token's expiry
        with _open(client, world.SHARED, thread) as (gymer, _):
            gymer.send_json({"type": "send", "text": "Still here"})
            assert coach.receive_json()["items"][0]["text"] == "Still here"


def test_a_socket_whose_token_expires_unrenewed_is_closed(client, relationships, monkeypatch):
    """With no renewal, the server closes the socket at the token's expiry."""
    # A token's expiry is in whole seconds, so with 2 seconds it lives more than 1.
    monkeypatch.setattr(config, "CHAT_TOKEN_TTL_SECONDS", 2)
    with _open(client, world.COACH_A, relationships[world.SHARED]) as (coach, _):
        assert _closed_with(coach) == config.CHAT_CLOSE_REFUSED


@pytest.mark.parametrize("who", ["another user", "another thread", "expired", "forged"])
def test_a_bad_renewal_closes_the_socket(client, relationships, who):
    """A renewal is verified like the first token; another user's or thread's closes the socket."""
    thread = relationships[world.SHARED]
    renewal = {
        "another user": _token(world.SHARED, thread),
        "another thread": _token(world.COACH_A, relationships[world.UNSHARED]),
        "expired": _token(world.COACH_A, thread, now=time.time() - 10**4),
        "forged": _forged(_token(world.COACH_A, thread)),
    }[who]
    with _open(client, world.COACH_A, thread) as (coach, _):
        coach.send_json(_auth(renewal))
        assert _closed_with(coach) == config.CHAT_CLOSE_REFUSED


def test_a_renewal_catches_up_from_the_page_s_last_id(client, relationships, store_conn):
    """With each token the page's last ID comes along, and the later messages are sent first."""
    thread = relationships[world.SHARED]
    with _open(client, world.COACH_A, thread) as (coach, _):
        first = _send(store_conn, world.SHARED, thread, "while asleep 1")
        second = _send(store_conn, world.SHARED, thread, "while asleep 2")
        assert [i["id"] for i in _probe(coach, world.COACH_A, thread, first)] == [second]


# --- Access checked before each push -------------------------------------------------------------


def test_after_the_relationship_ends_on_an_open_socket_nothing_is_sent_or_pushed(
    client, relationships, store_conn
):
    """The end while both sockets are open: the send is refused, the other side gets nothing."""
    thread = relationships[world.SHARED]
    with (
        _open(client, world.COACH_A, thread) as (coach, _),
        _open(client, world.SHARED, thread) as (gymer, _),
    ):
        users.end_relationship(store_conn, world.SHARED, thread)
        gymer.send_json({"type": "send", "text": CANARY})
        assert gymer.receive_json() == {"type": "error", "code": config.CHAT_ERROR_NOT_SENT}
        assert _probe(coach, world.COACH_A, thread, 0) == []
    assert messages.list_messages(store_conn, world.COACH_A, thread) == []


def test_a_recipient_who_lost_access_gets_no_push_and_is_closed(client, relationships, monkeypatch):
    """The push reads through the store's side check; a NotFound there closes that socket."""
    thread = relationships[world.SHARED]
    real = messages.list_messages

    def coach_lost_access(conn, reader_id, relationship_id, **kwargs):
        """Refuse the coach from the first push on, as the store does for a former side."""
        if reader_id == world.COACH_A and kwargs.get("after_id", 0) == 0 and pushing:
            raise NotFound
        return real(conn, reader_id, relationship_id, **kwargs)

    pushing = False
    monkeypatch.setattr(messages, "list_messages", coach_lost_access)
    with (
        _open(client, world.COACH_A, thread) as (coach, _),
        _open(client, world.SHARED, thread) as (gymer, _),
    ):
        pushing = True
        gymer.send_json({"type": "send", "text": CANARY})
        assert gymer.receive_json()["items"][0]["text"] == CANARY
        assert _closed_with(coach) == config.CHAT_CLOSE_REFUSED


def test_a_store_refusal_gives_the_sender_the_fixed_error_only(client, relationships):
    """An empty or too long message: the fixed code, never the store's reason."""
    with _open(client, world.SHARED, relationships[world.SHARED]) as (gymer, _):
        for text in ("   ", "x" * (config.MESSAGE_MAX_CHARS + 1), 42):
            gymer.send_json({"type": "send", "text": text})
            assert gymer.receive_json() == {"type": "error", "code": config.CHAT_ERROR_NOT_SENT}


# --- Notifications -------------------------------------------------------------------------------


def test_the_other_side_s_sockets_on_other_threads_get_a_notification_without_text(
    client, relationships
):
    """The coach, on another client's thread, gets the kind and the thread only."""
    thread = relationships[world.SHARED]
    with (
        _open(client, world.COACH_A, relationships[world.UNSHARED]) as (coach, _),
        _open(client, world.SHARED, thread) as (gymer, _),
    ):
        gymer.send_json({"type": "send", "text": CANARY})
        gymer.receive_json()
        assert coach.receive_json() == {
            "type": "notification",
            "kind": "message_received",
            "thread": thread,
        }


def test_no_one_but_the_thread_s_sides_is_notified(client, relationships):
    """A coach of another client gets nothing."""
    thread = relationships[world.SHARED]
    other = relationships[world.OTHERS]
    with (
        _open(client, world.COACH_B, other) as (stranger, _),
        _open(client, world.SHARED, thread) as (gymer, _),
    ):
        gymer.send_json({"type": "send", "text": CANARY})
        gymer.receive_json()
        assert _probe(stranger, world.COACH_B, other, 0) == []


def test_the_sender_s_own_socket_on_another_thread_gets_no_notification(client, relationships):
    """A coach sends on one client's thread; the coach's tab on another thread is not told."""
    thread = relationships[world.SHARED]
    other = relationships[world.UNSHARED]
    with (
        _open(client, world.COACH_A, other) as (other_tab, _),
        _open(client, world.COACH_A, thread) as (coach, _),
    ):
        coach.send_json({"type": "send", "text": "See you Monday"})
        coach.receive_json()
        assert _probe(other_tab, world.COACH_A, other, 0) == []


def test_a_message_stored_while_a_socket_catches_up_is_not_missed(
    client, relationships, monkeypatch
):
    """The new socket is in the hub before its catch-up reads, so a message sent then is pushed."""
    thread = relationships[world.SHARED]
    real = messages.list_messages
    real_push = chat_app._push_one
    read_done, go_on, push_queued = threading.Event(), threading.Event(), threading.Event()

    async def noted_push(path, hub, socket):
        """Note that the push to the coach started; it then waits on the coach's lock."""
        if socket.user_id == world.COACH_A:
            push_queued.set()
        await real_push(path, hub, socket)

    def slow_first_read(conn, reader_id, relationship_id, **kwargs):
        """Read the coach's first catch-up, then wait before returning it (a slow page load)."""
        rows = real(conn, reader_id, relationship_id, **kwargs)
        if reader_id == world.COACH_A and not read_done.is_set():
            read_done.set()
            go_on.wait(timeout=10)
        return rows

    with _open(client, world.SHARED, thread) as (gymer, _):
        monkeypatch.setattr(messages, "list_messages", slow_first_read)
        monkeypatch.setattr(chat_app, "_push_one", noted_push)
        with client.websocket_connect(PATH, headers={"origin": ORIGIN}) as coach:
            coach.send_json(_auth(_token(world.COACH_A, thread)))
            assert read_done.wait(timeout=10)
            # The coach's catch-up has read the thread (empty) and not yet returned.
            gymer.send_json({"type": "send", "text": "Running late"})
            # The message is stored and its push to the coach waits for the coach's lock.
            assert push_queued.wait(timeout=10)
            go_on.set()
            # A renewal from a made-up later ID sends nothing old, so only a push brings it.
            coach.send_json(_auth(_token(world.COACH_A, thread), 10**9))
            items = []
            readies = 0
            while readies < 2:
                frame = coach.receive_json()
                if frame["type"] == "ready":
                    readies += 1
                else:
                    items.extend(frame["items"])
    assert [item["text"] for item in items] == ["Running late"]


def test_a_renewal_with_an_older_id_never_sends_a_message_again(client, relationships):
    """A renewal with the ID before a pushed frame (still on its way) repeats nothing."""
    thread = relationships[world.SHARED]
    with (
        _open(client, world.COACH_A, thread) as (coach, _),
        _open(client, world.SHARED, thread) as (gymer, _),
    ):
        gymer.send_json({"type": "send", "text": "Message six"})
        assert coach.receive_json()["items"][0]["text"] == "Message six"
        # The renewal timer still had the ID before that message.
        assert _probe(coach, world.COACH_A, thread, 0) == []


def test_a_recipient_who_deleted_their_data_gets_nothing(client, relationships, store_conn):
    """The coach's data deleted while their socket is open: the send is refused, nothing pushed."""
    thread = relationships[world.SHARED]
    with (
        _open(client, world.COACH_A, thread) as (coach, _),
        _open(client, world.SHARED, thread) as (gymer, _),
    ):
        my_data.delete_user_data(store_conn, world.COACH_A, world.no_threads)
        gymer.send_json({"type": "send", "text": CANARY})
        assert gymer.receive_json() == {"type": "error", "code": config.CHAT_ERROR_NOT_SENT}
        coach.send_json(_auth(_token(world.COACH_A, thread)))
        assert _closed_with(coach) == config.CHAT_CLOSE_REFUSED  # no longer a side: refused


def test_a_store_error_in_the_notification_check_leaves_the_sender_s_socket_open(
    client, relationships, monkeypatch, log_stream
):
    """The message is stored and pushed; a failed check for another tab is logged, not fatal."""
    thread = relationships[world.SHARED]
    real = messages.list_messages

    def busy_for_one_check(conn, reader_id, relationship_id, **kwargs):
        """Fail the notification check (limit=1) as a store busy past its timeout would."""
        if kwargs.get("limit") == 1:
            raise sqlite3.OperationalError(f"database is locked {CANARY}")
        return real(conn, reader_id, relationship_id, **kwargs)

    with (
        _open(client, world.COACH_A, relationships[world.UNSHARED]) as (coach, _),
        _open(client, world.SHARED, thread) as (gymer, _),
    ):
        monkeypatch.setattr(messages, "list_messages", busy_for_one_check)
        gymer.send_json({"type": "send", "text": "Done"})
        assert gymer.receive_json()["items"][0]["text"] == "Done"
        assert _probe(gymer, world.SHARED, thread, 10**9) == []  # still open
        assert _probe(coach, world.COACH_A, relationships[world.UNSHARED], 10**9) == []
    assert '"event": "chat_error"' in log_stream.getvalue()
    assert CANARY not in log_stream.getvalue()


# --- Errors and logs -----------------------------------------------------------------------------


def test_an_error_inside_the_handler_closes_with_the_fixed_code_and_logs_only_its_diagnostic(
    client, relationships, monkeypatch, log_stream
):
    """A store error with the canary in its message: code 1011, a chat_error line, no canary."""

    def broken(*args, **kwargs):
        """Fail as a store error whose message quotes the message's text."""
        raise RuntimeError(f"cannot store {CANARY}")

    monkeypatch.setattr(messages, "send_message", broken)
    with _open(client, world.SHARED, relationships[world.SHARED]) as (gymer, _):
        gymer.send_json({"type": "send", "text": CANARY})
        assert _closed_with(gymer) == config.CHAT_CLOSE_ERROR
    lines = [json.loads(line) for line in log_stream.getvalue().splitlines()]
    errors = [line for line in lines if line["event"] == "chat_error"]
    assert errors and errors[0]["diagnostic"].startswith("RuntimeError in ")
    assert CANARY not in log_stream.getvalue()


@pytest.mark.parametrize("error", [sqlite3.OperationalError, db.StoreError])
def test_a_store_failure_on_send_gives_not_sent_and_keeps_the_socket(
    client, relationships, monkeypatch, log_stream, error
):
    """The store busy or unavailable: the fixed not_sent, the socket open, a chat_error line."""
    thread = relationships[world.SHARED]

    def failing(*args, **kwargs):
        """Fail as the store does, with the canary in the error's message."""
        raise error(f"database is locked {CANARY}")

    real = messages.send_message
    monkeypatch.setattr(messages, "send_message", failing)
    with _open(client, world.SHARED, thread) as (gymer, _):
        gymer.send_json({"type": "send", "text": CANARY})
        assert gymer.receive_json() == {"type": "error", "code": config.CHAT_ERROR_NOT_SENT}
        monkeypatch.setattr(messages, "send_message", real)
        assert _probe(gymer, world.SHARED, thread, 0) == []  # still open, nothing was stored
    lines = [json.loads(line) for line in log_stream.getvalue().splitlines()]
    assert [line["event"] for line in lines].count("chat_error") == 1
    assert CANARY not in log_stream.getvalue()


def test_the_log_lines_hold_no_text_token_user_or_thread(client, relationships, log_stream):
    """Normal and refused traffic: every line is allowlisted JSON with no data of the chat."""
    thread = relationships[world.SHARED]
    token = _token(world.SHARED, thread)
    with _open(client, world.COACH_A, thread) as (coach, _):
        with client.websocket_connect(PATH, headers={"origin": ORIGIN}) as gymer:
            gymer.send_json(_auth(token))
            _until_ready(gymer)
            gymer.send_json({"type": "send", "text": CANARY})
            gymer.receive_json()
            coach.receive_json()
            gymer.send_json({"type": "send", "text": ""})
            gymer.receive_json()
        with client.websocket_connect(PATH, headers={"origin": ORIGIN}) as bad:
            bad.send_json(_auth(_forged(token)))
            _closed_with(bad)
    text = log_stream.getvalue()
    lines = [json.loads(line) for line in text.splitlines()]
    assert {line["event"] for line in lines} >= {"chat_connection", "chat_message"}
    for forbidden in (
        CANARY,
        token,
        token.split(".")[2],
        world.SHARED,
        world.COACH_A,
        "testclient",
    ):
        assert forbidden not in text
    for line in lines:
        assert set(line) <= {"ts", "level", "logger", "event"} | observability.ALLOWED_FIELDS
        assert line.get("thread") is None


# --- The app itself ------------------------------------------------------------------------------


def test_fastapi_s_telemetry_and_docs_are_off(relationships, secret, monkeypatch):
    """No OpenTelemetry spans, metrics or logs (even with its environment switch), no docs pages."""
    monkeypatch.setenv("FASTAPI_OTEL_AUTO_CONFIGURE", "true")
    app = _chat_app()
    assert not app._native_telemetry.enabled()
    for name in ("tracing", "metrics", "logs", "operation_spans", "auto_configure"):
        assert app._telemetry[name] is False
    with TestClient(app) as test_client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert test_client.get(path).status_code == 404
