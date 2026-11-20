"""Tests for the chat server's process (T11.4a, D24): a real uvicorn server, its logs and main().

FastAPI's TestClient never runs uvicorn's protocol code, which writes the handshake lines (with the
client's address) and the tracebacks of uncaught errors; these tests run a real `uvicorn.Server`
bound to 127.0.0.1 on a free port, in a thread, and talk to it with the `websockets` client.
"""

import io
import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import pytest
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import connect

from src import config, observability, tracing
from src.realtime import app as chat_app
from src.realtime import server as chat_server
from src.realtime import tokens
from src.store import messages
from tests import store_world as world
from tests.fakes import patch_config

ROOT = Path(__file__).resolve().parent.parent
SECRET = "test-chat-secret-" + "x" * 32
ORIGIN = "http://localhost:8501"
CANARY = "CANARY-uvicorn-7f3e"


@pytest.fixture
def library_loggers_are_reset():
    """Put the library loggers the server routes back as they were after the test."""
    saved = {}
    for name in chat_server.LIBRARY_LOGGERS:
        library = logging.getLogger(name)
        saved[name] = (list(library.handlers), library.level, library.propagate)
    yield
    for name, (handlers, level, propagate) in saved.items():
        library = logging.getLogger(name)
        library.handlers, library.level, library.propagate = handlers, level, propagate


@pytest.fixture
def relationships(store_conn):
    """Build the made-up world in the test's store; return its relationship IDs by gymer."""
    return world.build(store_conn)


@pytest.fixture
def secret(monkeypatch):
    """Give the server a test secret through the one config function."""
    patch_config(monkeypatch, "chat_token_secret", lambda: SECRET)


@contextmanager
def _running(stream: io.StringIO):
    """Run a real uvicorn server for the chat app on a free port; yield its ws:// URL."""
    observability.configure_logging(stream=stream)
    server = chat_server.build_server(chat_app.create_app(config.STORE_PATH), port=0)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "the server did not start"
        time.sleep(0.02)
    host, port = server.servers[0].sockets[0].getsockname()[:2]
    try:
        yield host, port
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _url(port: int, path: str = config.CHAT_SOCKET_PATH) -> str:
    """Return the socket's URL on the test server."""
    return f"ws://127.0.0.1:{port}{path}"


def _auth(user: str, thread: int) -> str:
    """Return an auth frame for this user and thread as text."""
    token = tokens.mint(user, thread, SECRET)
    return json.dumps({"type": "auth", "token": token, "after_id": 0})


def _until_ready(socket) -> list[dict]:
    """Return the frames received before the next ready frame."""
    frames = []
    while (frame := json.loads(socket.recv(timeout=5)))["type"] != "ready":
        frames.append(frame)
    return frames


def _close_code(socket) -> int:
    """Return the close code the server sent next."""
    with pytest.raises(ConnectionClosed) as closed:
        socket.recv(timeout=5)
    return closed.value.rcvd.code


def test_the_server_binds_to_localhost_only(relationships, secret, library_loggers_are_reset):
    """The listening socket is on 127.0.0.1, never on every interface."""
    with _running(io.StringIO()) as (host, _port):
        assert host == "127.0.0.1"
    assert config.CHAT_SERVER_HOST == "127.0.0.1"


def test_a_real_server_delivers_a_message_between_two_sockets(
    relationships, secret, library_loggers_are_reset
):
    """Through uvicorn's own protocol code: the gymer's message reaches the coach's socket."""
    thread = relationships[world.SHARED]
    with _running(io.StringIO()) as (_host, port):
        with connect(_url(port), origin=ORIGIN) as coach, connect(_url(port), origin=ORIGIN) as gym:
            coach.send(_auth(world.COACH_A, thread))
            gym.send(_auth(world.SHARED, thread))
            _until_ready(coach), _until_ready(gym)
            gym.send(json.dumps({"type": "send", "text": "Squats done"}))
            frame = json.loads(coach.recv(timeout=5))
    assert frame["items"][0]["text"] == "Squats done" and frame["items"][0]["mine"] is False


def test_no_line_the_server_writes_holds_a_canary_token_or_address(
    relationships, secret, library_loggers_are_reset, monkeypatch, capfd
):
    """Normal, refused and failing traffic on a real server: every line is JSON without data."""
    thread = relationships[world.SHARED]
    token = tokens.mint(world.SHARED, thread, SECRET)
    stream = io.StringIO()
    with _running(stream) as (_host, port):
        # Normal traffic.
        with connect(_url(port), origin=ORIGIN) as coach, connect(_url(port), origin=ORIGIN) as gym:
            coach.send(_auth(world.COACH_A, thread))
            gym.send(json.dumps({"type": "auth", "token": token, "after_id": 0}))
            _until_ready(coach), _until_ready(gym)
            gym.send(json.dumps({"type": "send", "text": CANARY}))
            coach.recv(timeout=5)
            gym.recv(timeout=5)
        # Refused traffic: a forged token, a token in the query string, a foreign origin, an
        # oversized frame, a plain HTTP request with the canary in its path and query string.
        with connect(_url(port), origin=ORIGIN) as bad:
            bad.send(json.dumps({"type": "auth", "token": token[:-2] + CANARY, "after_id": 0}))
            assert _close_code(bad) == config.CHAT_CLOSE_REFUSED
        with pytest.raises(InvalidStatus):
            connect(_url(port, f"{config.CHAT_SOCKET_PATH}?token={token}"), origin=ORIGIN)
        with pytest.raises(InvalidStatus):
            connect(_url(port), origin=f"http://{CANARY}.example")
        with connect(_url(port), origin=ORIGIN) as big:
            big.send(CANARY * (config.CHAT_MAX_FRAME_BYTES // len(CANARY) + 10))
            with pytest.raises(ConnectionClosed):
                big.recv(timeout=5)
        with pytest.raises(OSError):
            urllib.request.urlopen(f"http://127.0.0.1:{port}/{CANARY}?q={CANARY}", timeout=5)
        # A handler that raises an error with the canary in its message.

        def broken(*args, **kwargs):
            """Fail as a store error whose message quotes the message's text."""
            raise RuntimeError(f"cannot store {CANARY}")

        monkeypatch.setattr(messages, "send_message", broken)
        with connect(_url(port), origin=ORIGIN) as gym:
            gym.send(json.dumps({"type": "auth", "token": token, "after_id": 0}))
            _until_ready(gym)
            gym.send(json.dumps({"type": "send", "text": CANARY}))
            assert _close_code(gym) == config.CHAT_CLOSE_ERROR
    written = stream.getvalue()
    captured = capfd.readouterr()
    everything = written + captured.out + captured.err
    for forbidden in (CANARY, token, token.split(".")[2], world.SHARED, "127.0.0.1", "Traceback"):
        assert forbidden not in everything, forbidden
    lines = [json.loads(line) for line in written.splitlines()]
    assert lines, "the server wrote no line at all"
    for line in lines:
        assert set(line) <= {"ts", "level", "logger", "event"} | observability.ALLOWED_FIELDS
    assert any(line["event"] == "chat_error" for line in lines)
    # Only the app's JSON lines: nothing on stdout or stderr in uvicorn's own format.
    assert captured.out == "" and captured.err == ""


def test_uvicorn_s_loggers_write_only_warnings_through_the_json_formatter(
    library_loggers_are_reset,
):
    """After build_server(), every library logger is at WARNING, with the app's handler only."""
    stream = io.StringIO()
    observability.configure_logging(stream=stream)
    chat_server.build_server(chat_app.create_app(config.STORE_PATH), port=0)
    for name in chat_server.LIBRARY_LOGGERS:
        library = logging.getLogger(name)
        assert library.level == logging.WARNING and library.propagate is False
        assert [getattr(h, "is_app_handler", False) for h in library.handlers] == [True]
    # A uvicorn handshake line at INFO is dropped; an error line keeps neither text nor traceback.
    logging.getLogger("uvicorn.error").info('%s - "WebSocket /ws" [accepted]', ("127.0.0.1", 5))
    try:
        raise RuntimeError(CANARY)
    except RuntimeError:
        logging.getLogger("uvicorn.error").exception("Exception in ASGI application %s", CANARY)
    [line] = [json.loads(text) for text in stream.getvalue().splitlines()]
    assert line == {**line, "event": observability.UNNAMED_EVENT, "logger": "uvicorn.error"}
    assert CANARY not in stream.getvalue() and "127.0.0.1" not in stream.getvalue()


def test_the_server_s_settings_keep_uvicorn_quiet(library_loggers_are_reset):
    """Access log off, no proxy headers, no server header, frames capped, localhost."""
    observability.configure_logging(stream=io.StringIO())
    server = chat_server.build_server(chat_app.create_app(config.STORE_PATH))
    settings = server.config
    assert settings.access_log is False and settings.proxy_headers is False
    assert settings.host == "127.0.0.1" and settings.port == config.CHAT_SERVER_PORT
    assert settings.server_header is False and settings.ws_max_size == config.CHAT_MAX_FRAME_BYTES


def test_reading_the_secret_outside_streamlit_writes_nothing_to_stderr(tmp_path):
    """No secrets.toml, the secret in the environment: read with no Streamlit warning printed."""
    # In a fresh process whose working folder and home have no .streamlit/, as the chat server's
    # process reads st.secrets outside a Streamlit runtime.
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        config.CHAT_TOKEN_SECRET_ENV_NAME: SECRET,
    }
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            "from src import config; print(config.chat_token_secret() is not None)",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0 and done.stdout.strip() == "True"
    assert done.stderr == ""


# --- main() --------------------------------------------------------------------------------------


@pytest.fixture
def no_run(monkeypatch):
    """Replace uvicorn's run with a recorder, so main() never opens a port; return the calls."""
    runs = []
    monkeypatch.setattr(chat_server.uvicorn.Server, "run", lambda self: runs.append(self))
    return runs


def _main_lines(capsys) -> list[dict]:
    """Return the JSON lines main() wrote to stderr."""
    return [json.loads(line) for line in capsys.readouterr().err.splitlines()]


def test_main_never_sets_up_tracing_whatever_the_flags_say(
    monkeypatch, secret, relationships, no_run, library_loggers_are_reset
):
    """Tracing, its key and the demo flag all on: tracing is turned off, no client installed."""
    patch_config(monkeypatch, "tracing_requested", lambda: True)
    patch_config(monkeypatch, "get_langsmith_api_key", lambda: "lsv2-test-not-a-real-key")
    patch_config(monkeypatch, "tracing_demo_unmasked", lambda: True)
    patch_config(monkeypatch, "demo_mode", lambda: True)

    set_up, turned_off = [], []
    real_set_up, real_turn_off = tracing.configure_tracing, tracing.turn_off_tracing
    # Recorded, not refused: conftest's teardown calls configure_tracing() to reset the state.
    monkeypatch.setattr(tracing, "configure_tracing", lambda: set_up.append(real_set_up()))
    monkeypatch.setattr(tracing, "turn_off_tracing", lambda: turned_off.append(real_turn_off()))
    assert chat_server.main(["--store", str(config.STORE_PATH)]) == 0
    assert set_up == [] and turned_off == [None] and len(no_run) == 1
    assert tracing._installed["key_digest"] is None and not tracing.demo_gate_open()


def test_main_refuses_to_start_without_a_secret(
    monkeypatch, no_run, capsys, library_loggers_are_reset
):
    """No secret: exit status 2, a fixed reason, no server."""
    patch_config(monkeypatch, "chat_token_secret", lambda: None)
    assert chat_server.main([]) == 2 and no_run == []
    [line] = _main_lines(capsys)
    assert line["event"] == "chat_server" and line["reason"] == "no_secret"


def test_main_in_demo_mode_needs_the_store_s_path(
    monkeypatch, secret, no_run, capsys, library_loggers_are_reset
):
    """Demo mode's store is the Streamlit process's temporary file, so --store must name it."""
    patch_config(monkeypatch, "demo_mode", lambda: True)
    assert chat_server.main([]) == 2 and no_run == []
    assert _main_lines(capsys)[0]["reason"] == "demo_store"


def test_main_never_creates_a_store_file(
    monkeypatch, secret, no_run, capsys, tmp_path, library_loggers_are_reset
):
    """A path with no file is refused: the server opens only a store the app already made."""
    missing = tmp_path / "missing.sqlite3"
    assert chat_server.main(["--store", str(missing)]) == 2 and no_run == []
    assert not missing.exists()
    assert _main_lines(capsys)[0]["reason"] == "no_store"


def test_main_serves_the_named_store_on_localhost(
    monkeypatch, secret, relationships, no_run, capsys, library_loggers_are_reset
):
    """With a secret and an existing store, main() runs uvicorn on 127.0.0.1."""
    patch_config(monkeypatch, "demo_mode", lambda: True)
    assert chat_server.main(["--store", str(config.STORE_PATH), "--port", "8599"]) == 0
    [server] = no_run
    assert server.config.host == "127.0.0.1" and server.config.port == 8599
    line = _main_lines(capsys)[-1]
    assert line["event"] == "chat_server" and line["status"] == "started"
