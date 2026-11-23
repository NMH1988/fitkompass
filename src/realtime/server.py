"""Mount the chat app on Streamlit's own server (T11.4b, D24): one process, one port, one command.

`serve.py` builds `st.App` for app.py with `chat_routes()` and `quiet_library_logs`, written out in
serve.py itself (`streamlit run` finds the app by reading the file for `app = st.App(...)`), and
`streamlit run serve.py` serves the pages with the chat socket at
`config.CHAT_MOUNT_PATH` + `config.CHAT_SOCKET_PATH`, on the host and port Streamlit serves (bound
by `.streamlit/config.toml` to this machine). `streamlit run app.py` alone serves the pages without
the socket, and the Messages page says real-time messages are off (`mounted()`).

The socket shares Streamlit's process, its store and its logging. When the server has started (the
lifespan hook, after uvicorn set up its own loggers), uvicorn's, the web libraries' and asyncio's
loggers write through the app's JSON formatter at WARNING only, so a handshake line with a client's
address (INFO), a request line or a traceback never reaches stderr; this holds for Streamlit's own
socket too. The chat routes run no model, so nothing they do is traced.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import streamlit as st
from starlette.routing import Mount

from src import config, observability
from src.realtime import page
from src.realtime.app import create_app

# Every logger uvicorn and the libraries under it write to: its server and protocol lines, the
# WebSocket library's, FastAPI's and Starlette's, and asyncio's "exception was never retrieved".
LIBRARY_LOGGERS = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "uvicorn.asgi",
    "websockets",
    "fastapi",
    "starlette",
    "asyncio",
)

# Set by chat_routes(): read by the Messages page to tell a run with the socket from one without.
_MOUNTED = {"chat": False}


def mounted() -> bool:
    """Return True if this process serves the chat socket (started through serve.py)."""
    return _MOUNTED["chat"]


def serving_port() -> int:
    """Return the port Streamlit serves: the one it bound, after moving off a taken one."""
    return int(st.get_option("server.port"))


def current_origins() -> frozenset[str]:
    """Return the origins allowed to open the socket now."""
    return page.allowed_origins(serving_port())


@asynccontextmanager
async def quiet_library_logs(_app: object) -> AsyncIterator[None]:
    """Route the library loggers through the app's JSON formatter once the server has started."""
    # Here and not at import: uvicorn sets its loggers up when the server is built, after serve.py
    # is imported, and would undo this.
    observability.configure_logging()
    observability.capture_library_logs(LIBRARY_LOGGERS)
    yield


def chat_routes(store_path: Callable[[], Path]) -> list[Mount]:
    """Return the chat route for st.App, on the store `store_path()` names; mark the process."""
    _MOUNTED["chat"] = True
    return [Mount(config.CHAT_MOUNT_PATH, app=create_app(store_path, current_origins))]
