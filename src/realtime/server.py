"""Run the chat server (T11.4a, D24): uvicorn on this machine only, with the app's own log lines.

`python -m src.realtime [--store PATH] [--port N]` starts it next to the Streamlit app. It reads and
writes the same store file: `config.STORE_PATH` by default; in demo mode the store is a temporary
file the Streamlit process makes, so `--store` must name it (T11.4b's launcher does), and the server
refuses to start without it. It also refuses without the token secret or a store file that exists
(it never creates one). Tracing is off in its process (no model runs there). uvicorn's access log
is off; its own loggers, and asyncio's, write through the JSON formatter at WARNING only, so a
handshake line with the client's address (INFO), a request line or a traceback never reaches stderr.
"""

import argparse
import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from src import config, observability
from src.realtime.app import create_app

logger = logging.getLogger(__name__)

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


def build_server(app: FastAPI, *, port: int | None = None) -> uvicorn.Server:
    """Return a uvicorn server for the app, bound to localhost, with its own logging kept quiet."""
    server_config = uvicorn.Config(
        app,
        host=config.CHAT_SERVER_HOST,
        port=config.CHAT_SERVER_PORT if port is None else port,
        # uvicorn installs no log handlers of its own; capture_library_logs() routes its loggers.
        log_config=None,
        log_level="warning",
        access_log=False,
        ws="websockets-sansio",
        ws_max_size=config.CHAT_MAX_FRAME_BYTES,
        # Nothing is trusted from a proxy (there is none), and no header names the server.
        proxy_headers=False,
        server_header=False,
        date_header=False,
        lifespan="off",
    )
    # After uvicorn's Config, which sets its loggers' levels when it is built.
    observability.capture_library_logs(LIBRARY_LOGGERS)
    return uvicorn.Server(server_config)


def _store_path(store: Path | None) -> Path | None:
    """Return the store file to serve, or None when demo mode names none (it is refused)."""
    if store is not None:
        return store
    return None if config.demo_mode() else config.STORE_PATH


def _refuse(reason: str) -> int:
    """Log why the server did not start (a fixed code) and return the exit status."""
    logger.warning("chat_server", extra={"status": "refused", "reason": reason})
    return 2


def main(argv: list[str] | None = None) -> int:
    """Start the chat server; return 2 without a secret, a store file, or --store in demo mode."""
    # No tracing in this process: it runs no model, so there is nothing to trace, and with no
    # LangSmith client installed a later change cannot start tracing here by accident.
    observability.configure_logging(with_tracing=False)
    parser = argparse.ArgumentParser(prog="python -m src.realtime", description=__doc__)
    parser.add_argument("--store", type=Path, help="the store file (required in demo mode)")
    parser.add_argument("--port", type=int, default=None, help="the port on 127.0.0.1")
    args = parser.parse_args(argv)
    if config.chat_token_secret() is None:
        return _refuse("no_secret")
    store = _store_path(args.store)
    if store is None:
        return _refuse("demo_store")
    if not store.is_file():
        return _refuse("no_store")
    server = build_server(create_app(store), port=args.port)
    logger.info("chat_server", extra={"status": "started"})
    server.run()
    return 0
