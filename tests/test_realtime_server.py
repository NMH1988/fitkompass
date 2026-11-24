"""Tests for the chat socket mounted on Streamlit's own server (T11.4a, T11.4b, D24).

FastAPI's TestClient never runs uvicorn's protocol code, which writes the handshake lines (with the
client's address) and the tracebacks of uncaught errors. These tests start a real Streamlit server
with `streamlit run` in a child process, through a wrapper like serve.py that mounts the chat app
with `server.chat_routes()`, bound to 127.0.0.1 on a free port, and talk to it with the `websockets`
client. The child's working folder and home are a temporary folder, and its page script is a tiny
one there, so it reads no secrets file of the repo; the secret comes from its environment.
"""

import io
import json
import logging
import os
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import pytest
import uvicorn
from starlette.routing import Mount
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import connect

from src import config, observability
from src.realtime import page as realtime_page
from src.realtime import server as chat_server
from src.realtime import tokens
from tests import store_world as world

ROOT = Path(__file__).resolve().parent.parent
SECRET = "test-chat-secret-" + "x" * 32
CANARY = "CANARY-uvicorn-7f3e"
PATH = config.CHAT_MOUNT_PATH + config.CHAT_SOCKET_PATH
# The child's wrapper: serve.py's call with a test store, and, with BROKEN set, a store write that
# fails with the canary in its message.
WRAPPER = """
import os
from pathlib import Path

from src.realtime import server
from src.store import messages

if os.environ.get("FITKOMPASS_TEST_BROKEN"):
    def broken(*args, **kwargs):
        raise RuntimeError("cannot store " + os.environ["FITKOMPASS_TEST_CANARY"])
    messages.send_message = broken

import streamlit as st

app = st.App(
    str(Path(__file__).with_name("page.py")),
    routes=server.chat_routes(store_path=lambda: Path(os.environ["FITKOMPASS_TEST_STORE"])),
    lifespan=server.quiet_library_logs,
)
"""


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


def _free_port() -> int:
    """Return a port on 127.0.0.1 that is free now."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@contextmanager
def _streamlit(tmp_path: Path, *, broken: bool = False):
    """Run `streamlit run` on a wrapper like serve.py in a child process; yield port and logs."""
    (tmp_path / "page.py").write_text('import streamlit as st\n\nst.write("page")\n', "utf-8")
    wrapper = tmp_path / "wrapper.py"
    wrapper.write_text(WRAPPER, encoding="utf-8")
    port = _free_port()
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        config.CHAT_TOKEN_SECRET_ENV_NAME: SECRET,
        "FITKOMPASS_TEST_STORE": str(config.STORE_PATH),
        "FITKOMPASS_TEST_CANARY": CANARY,
    }
    env.pop("FITKOMPASS_TEST_BROKEN", None)
    if broken:
        env["FITKOMPASS_TEST_BROKEN"] = "1"
    out, err = tmp_path / "stdout.txt", tmp_path / "stderr.txt"
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(wrapper),
        "--server.address",
        "127.0.0.1",
        "--server.port",
        str(port),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
        "--global.developmentMode",
        "false",
    ]
    with out.open("w", encoding="utf-8") as stdout, err.open("w", encoding="utf-8") as stderr:
        child = subprocess.Popen(command, cwd=tmp_path, env=env, stdout=stdout, stderr=stderr)
        try:
            deadline = time.monotonic() + 90
            while True:
                assert child.poll() is None, err.read_text(encoding="utf-8")[-2000:]
                assert time.monotonic() < deadline, "streamlit did not start"
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/_stcore/health", timeout=2
                    ):
                        break
                except OSError:
                    time.sleep(0.2)
            logs = {"stdout": out, "stderr": err}
            yield port, logs
        finally:
            child.terminate()
            try:
                child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=20)


def _url(port: int, path: str = PATH) -> str:
    """Return the socket's URL on the test server."""
    return f"ws://127.0.0.1:{port}{path}"


def _origin(port: int) -> str:
    """Return the page's origin on the test server."""
    return f"http://localhost:{port}"


def _auth(user: str, thread: int) -> str:
    """Return an auth frame for this user and thread as text."""
    token = tokens.mint(user, thread, SECRET)
    return json.dumps({"type": "auth", "token": token, "after_id": 0})


def _until_ready(ws) -> list[dict]:
    """Return the frames received before the next ready frame."""
    frames = []
    while (frame := json.loads(ws.recv(timeout=10)))["type"] != "ready":
        frames.append(frame)
    return frames


def _close_code(ws) -> int:
    """Return the close code the server sent next."""
    with pytest.raises(ConnectionClosed) as closed:
        ws.recv(timeout=10)
    return closed.value.rcvd.code


def test_a_message_crosses_streamlit_s_own_port_and_a_foreign_origin_is_refused(
    relationships, tmp_path
):
    """Through `streamlit run` on the wrapper: one port serves the page and the chat socket."""
    thread = relationships[world.SHARED]
    with _streamlit(tmp_path) as (port, _logs):
        origin = _origin(port)
        with connect(_url(port), origin=origin) as coach, connect(_url(port), origin=origin) as gym:
            coach.send(_auth(world.COACH_A, thread))
            gym.send(_auth(world.SHARED, thread))
            _until_ready(coach), _until_ready(gym)
            gym.send(json.dumps({"type": "send", "text": "Squats done"}))
            frame = json.loads(coach.recv(timeout=10))
        # The page's own port only: the default 8501 is another port here, so it is refused.
        for foreign in (
            "http://localhost:8501",
            "http://evil.example",
            f"http://localhost:{port}0",
        ):
            with pytest.raises(InvalidStatus):
                connect(_url(port), origin=foreign)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10) as answer:
            assert answer.status == 200  # the page itself is still served
    assert frame["items"][0]["text"] == "Squats done" and frame["items"][0]["mine"] is False


def _no_data_in(logs: dict, forbidden: tuple[str, ...]) -> list[dict]:
    """Assert no child output holds a forbidden value; return the JSON lines it wrote to stderr."""
    out = logs["stdout"].read_text(encoding="utf-8")
    err = logs["stderr"].read_text(encoding="utf-8")
    for value in forbidden:
        assert value not in out and value not in err, value
    assert "Traceback" not in err and "connection open" not in err
    lines = []
    for text in err.splitlines():
        if text.strip():
            lines.append(json.loads(text))  # only the app's JSON lines on stderr
    for line in lines:
        assert set(line) <= {"ts", "level", "logger", "event"} | observability.ALLOWED_FIELDS
    return lines


def test_no_line_the_server_writes_holds_a_canary_token_or_address(relationships, tmp_path):
    """Normal and refused traffic on a real Streamlit server: no text, token or client address."""
    thread = relationships[world.SHARED]
    token = tokens.mint(world.SHARED, thread, SECRET)
    client_ports = []
    with _streamlit(tmp_path) as (port, logs):
        origin = _origin(port)
        with connect(_url(port), origin=origin) as coach, connect(_url(port), origin=origin) as gym:
            client_ports += [coach.local_address[1], gym.local_address[1]]
            coach.send(_auth(world.COACH_A, thread))
            gym.send(json.dumps({"type": "auth", "token": token, "after_id": 0}))
            _until_ready(coach), _until_ready(gym)
            gym.send(json.dumps({"type": "send", "text": CANARY}))
            coach.recv(timeout=10)
            gym.recv(timeout=10)
        # Refused traffic: a forged token, a token in the query string, a foreign origin, an
        # oversized frame, a plain HTTP request with the canary in its path and query string.
        with connect(_url(port), origin=origin) as bad:
            client_ports.append(bad.local_address[1])
            bad.send(json.dumps({"type": "auth", "token": token[:-2] + CANARY, "after_id": 0}))
            assert _close_code(bad) == config.CHAT_CLOSE_REFUSED
        with pytest.raises(InvalidStatus):
            connect(_url(port, f"{PATH}?token={token}"), origin=origin)
        with pytest.raises(InvalidStatus):
            connect(_url(port), origin=f"http://{CANARY}.example")
        with connect(_url(port), origin=origin) as big:
            big.send(CANARY * (config.CHAT_MAX_FRAME_BYTES // len(CANARY) + 10))
            with pytest.raises(ConnectionClosed):
                big.recv(timeout=10)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/{CANARY}?q={CANARY}", timeout=10)
        except OSError:
            pass
        time.sleep(0.5)  # the child writes its last lines
    forbidden = (CANARY, token, token.split(".")[2], world.SHARED, world.COACH_A)
    _no_data_in(logs, forbidden + tuple(f":{number}" for number in client_ports))


def test_a_handler_error_is_logged_by_its_diagnostic_only(relationships, tmp_path):
    """A store write that fails with the canary in its message: closed with 1011, no traceback."""
    thread = relationships[world.SHARED]
    token = tokens.mint(world.SHARED, thread, SECRET)
    with _streamlit(tmp_path, broken=True) as (port, logs):
        with connect(_url(port), origin=_origin(port)) as gym:
            gym.send(json.dumps({"type": "auth", "token": token, "after_id": 0}))
            _until_ready(gym)
            gym.send(json.dumps({"type": "send", "text": CANARY}))
            assert _close_code(gym) == config.CHAT_CLOSE_ERROR
        time.sleep(0.5)
    lines = _no_data_in(logs, (CANARY, token, world.SHARED))
    assert any(line["event"] == "chat_error" for line in lines)


def test_serve_py_mounts_the_chat_beside_app_py(tmp_path):
    """serve.py builds Streamlit's app for app.py with the chat mounted, on the pages' store."""
    # In a child process: building an st.App pins the process's script folder for config files.
    code = (
        "import serve; from src.realtime import server;"
        "routes = serve.app._user_routes;"
        "print(serve.app._script_path.name, [r.path for r in routes], server.mounted(),"
        " serve.app._user_lifespan is server.quiet_library_logs)"
    )
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
    }
    done = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120
    )
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip().splitlines()[-1] == f"app.py ['{config.CHAT_MOUNT_PATH}'] True True"


def test_chat_routes_mount_the_chat_and_mark_the_process(monkeypatch):
    """The chat app is mounted at the mount path; mounted() turns true only then."""
    monkeypatch.setitem(chat_server._MOUNTED, "chat", False)
    assert chat_server.mounted() is False
    [route] = chat_server.chat_routes(store_path=lambda: config.STORE_PATH)
    assert isinstance(route, Mount) and route.path == config.CHAT_MOUNT_PATH
    assert chat_server.mounted() is True


def test_serve_py_is_found_by_streamlit_run_as_an_asgi_app():
    """`streamlit run serve.py` reads the file for `app = st.App(...)`: it must find it there."""
    from streamlit.web.server.app_discovery import discover_asgi_app

    found = discover_asgi_app(ROOT / "serve.py")
    assert found.is_asgi_app and found.app_name == "app"


def test_the_allowed_origins_follow_the_port_streamlit_serves(monkeypatch):
    """Both local hosts on the served port, plus the public origins; nothing else."""
    assert realtime_page.allowed_origins(8502) == {"http://localhost:8502", "http://127.0.0.1:8502"}
    monkeypatch.setattr(config, "CHAT_PUBLIC_ORIGINS", frozenset({"https://app.example"}))
    assert "https://app.example" in realtime_page.allowed_origins(8501)
    monkeypatch.setattr(chat_server.st, "get_option", lambda name: 8503)
    assert "http://localhost:8503" in chat_server.current_origins()


def test_uvicorn_s_loggers_write_only_warnings_through_the_json_formatter(
    library_loggers_are_reset,
):
    """After uvicorn sets its loggers up, the lifespan hook routes them through the JSON handler."""
    import asyncio

    stream = io.StringIO()
    uvicorn.Config(lambda scope, receive, send: None)  # uvicorn's own logging config, at INFO
    observability.configure_logging(stream=stream)

    async def run_hook() -> None:
        """Enter and leave the lifespan hook."""
        async with chat_server.quiet_library_logs(None):
            pass

    asyncio.run(run_hook())
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


def test_reading_the_secret_outside_streamlit_writes_nothing_to_stderr(tmp_path):
    """No secrets.toml, the secret in the environment: read with no Streamlit warning printed."""
    # In a fresh process whose working folder and home have no .streamlit/, as a script would.
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
