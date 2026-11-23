"""The chat app (T11.4a, D24): one WebSocket that delivers coach-client messages.

It is mounted on Streamlit's own server (`src/realtime/server.py`, `serve.py`), so the socket is at
`config.CHAT_MOUNT_PATH` + `config.CHAT_SOCKET_PATH` on the page's host and port. A socket belongs
to one user and one thread, both taken only from a token that verifies (`tokens.verify()`), sent as
the socket's first message; nothing else the browser sends names a user or a thread. Before the
socket is accepted, the page's `Origin` must be on the allowlist (the local hosts on the port
Streamlit serves, and the public origins in config) and the URL must have no query string (a token
there would reach an access log). Then:

- the first frame is `{"type": "auth", "token": ..., "after_id": n}`, within
  `config.CHAT_AUTH_WAIT_SECONDS`; the token must verify and its user must be a side of its thread
  in the store, else the socket closes with `config.CHAT_CLOSE_REFUSED` before anything else is
  read;
- the server then sends the thread's messages after `after_id` (the last one the page shows), at
  most `config.CHAT_CATCH_UP_LIMIT`, with `"more": true` when there are later ones (the page then
  sends an `auth` frame again with its new last ID, or reads the thread from the store), then
  `{"type": "ready"}`. A push or a notification waiting on the socket may come between the
  catch-up and `ready`, so `ready` means "every stored message up to here was sent", not "only the
  catch-up came before";
- `{"type": "send", "text": ...}` stores a message through `src/store/messages.py` and pushes it to
  every open socket of that thread; the other side's sockets on other threads get a notification
  with the kind and the thread only, never the text. A message the store refuses, or cannot store
  (busy past its timeout, unavailable), gives the sender the fixed `config.CHAT_ERROR_NOT_SENT`,
  never the reason, and the socket stays open;
- an `auth` frame on an open socket renews it: its token is verified like the first, and a token for
  another user or thread closes the socket; its `after_id` only moves the socket forward, so a
  message already sent is never sent again; a socket whose token expires unrenewed is closed.

Every push reads the recipient's messages through `messages.list_messages()`, the store's read with
its own side check, so nothing reaches a user who is no longer a side of the thread. The browser
gets `mine` for each message, never a user ID. The handler catches every other error, logs only its
diagnostic and closes with `config.CHAT_CLOSE_ERROR`, so uvicorn never logs a traceback (which
could quote a message); no log line holds a message's text, a token or an address.
"""

import asyncio
import json
import logging
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from anyio import to_thread
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from src import config, llm
from src.realtime import page, tokens
from src.store import db, messages, values
from src.store.access import NotFound

logger = logging.getLogger(__name__)

# FastAPI's own OpenTelemetry spans, metrics and logs are off, whatever the environment says: its
# logs would record an error's message and stack trace, and its spans the path and query string.
_NO_TELEMETRY = {
    "tracing": False,
    "metrics": False,
    "logs": False,
    "operation_spans": False,
    "auto_configure": False,
}


class _Refused(Exception):  # noqa: N818 - a refusal, not a program error
    """Raised to close a socket with the refusal code; its argument is a fixed reason code."""


@dataclass(eq=False)
class _Socket:
    """One open socket: its verified user and thread, its token's expiry and the last ID sent."""

    websocket: WebSocket
    user_id: str
    thread_id: int
    expires_at: int
    last_id: int
    # One sender at a time: the socket's own task and another socket's push both send on it.
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class Hub:
    """The open sockets of this process, found by thread and by user."""

    def __init__(self) -> None:
        """Start with no sockets."""
        self._sockets: set[_Socket] = set()

    def add(self, socket: _Socket) -> None:
        """Register a socket that passed its token and store checks."""
        self._sockets.add(socket)

    def remove(self, socket: _Socket) -> None:
        """Forget a socket that closed."""
        self._sockets.discard(socket)

    def on_thread(self, thread_id: int) -> list[_Socket]:
        """Return the open sockets of a thread, either side's."""
        return [s for s in self._sockets if s.thread_id == thread_id]

    def elsewhere(self, thread_id: int, sender_id: str) -> list[_Socket]:
        """Return the sockets on other threads of every user but the sender."""
        return [s for s in self._sockets if s.thread_id != thread_id and s.user_id != sender_id]

    def __len__(self) -> int:
        """Return how many sockets are open."""
        return len(self._sockets)


@contextmanager
def _store(path: Path) -> Iterator[sqlite3.Connection]:
    """Open the store for one call, in the calling worker thread, and close it after."""
    # One connection per call, opened and closed in the thread that uses it: no connection is
    # shared between threads, and none holds a read open between calls (T11.3's note on the log).
    with db.connect(path) as conn:
        yield conn


async def _in_thread(path: Path, work: Callable[[sqlite3.Connection], Any]) -> Any:
    """Run one store call in a worker thread, so the event loop never waits on SQLite."""

    def run() -> Any:
        """Open the store and do the work."""
        with _store(path) as conn:
            return work(conn)

    return await to_thread.run_sync(run)


def _log_connection(status: str, reason: str | None = None) -> None:
    """Write one connection line: its status and a fixed reason code, nothing about the client."""
    logger.info("chat_connection", extra={"status": status, "reason": reason})


async def _receive(websocket: WebSocket, timeout: float) -> str | None:
    """Return the next text frame, None if none came in time; WebSocketDisconnect on a close."""
    if timeout <= 0:
        return None
    try:
        message = await asyncio.wait_for(websocket.receive(), timeout)
    except TimeoutError:
        return None
    if message["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(message.get("code", 1000))
    text = message.get("text")
    if not isinstance(text, str) or len(text.encode("utf-8")) > config.CHAT_MAX_FRAME_BYTES:
        raise _Refused("frame")  # a binary or oversized frame
    return text


def _parse(text: str) -> dict:
    """Return a frame's JSON object with a known type; _Refused for anything else."""
    try:
        frame = json.loads(text)
    except ValueError, RecursionError:  # not JSON, or nested too deep to parse
        raise _Refused("frame") from None
    if not isinstance(frame, dict) or frame.get("type") not in ("auth", "send"):
        raise _Refused("frame")
    return frame


def _auth(frame: dict, secret: str) -> tuple[tokens.Claims, int]:
    """Return the verified claims and the page's last message ID of an auth frame; else _Refused."""
    if frame.get("type") != "auth" or set(frame) != {"type", "token", "after_id"}:
        raise _Refused("frame")
    try:
        claims = tokens.verify(frame["token"], secret)
        after_id = values.whole_number(frame["after_id"], "after_id")
    except tokens.TokenRefused, values.StoreValueError:
        raise _Refused("token") from None
    return claims, after_id


async def _send_json(socket: _Socket, payload: dict) -> None:
    """Send one JSON frame on a socket."""
    await socket.websocket.send_text(json.dumps(payload))


async def _catch_up(path: Path, socket: _Socket, from_id: int | None = None) -> None:
    """Send the messages after the socket's last ID (or from_id if later), with the side check."""
    # Under the socket's lock, so two pushes never send the same message twice or out of order. A
    # renewal's `from_id` (the page's last ID) only moves the socket forward: a lower one means
    # frames already sent are still on their way to the page, and sending them again would repeat
    # them; a higher one lets a page that read the thread from the store skip ahead.
    async with socket.lock:
        if from_id is not None:
            socket.last_id = max(socket.last_id, from_id)
        rows = await _in_thread(
            path,
            lambda conn: messages.list_messages(
                conn,
                socket.user_id,
                socket.thread_id,
                after_id=socket.last_id,
                limit=config.CHAT_CATCH_UP_LIMIT + 1,
            ),
        )
        more = len(rows) > config.CHAT_CATCH_UP_LIMIT
        rows = rows[: config.CHAT_CATCH_UP_LIMIT]
        if rows:
            socket.last_id = rows[-1]["id"]
        if rows or more:
            await _send_json(
                socket,
                {"type": "messages", "items": page.items(rows, socket.user_id), "more": more},
            )


async def _ready(socket: _Socket) -> None:
    """Tell the page a token was taken and its catch-up is complete."""
    # After the catch-up's frames, so the page knows it holds every stored message up to here.
    async with socket.lock:
        await _send_json(socket, {"type": "ready"})


async def _close(websocket: WebSocket, code: int) -> None:
    """Close a socket with a fixed code, ignoring a socket that is already gone."""
    try:
        await websocket.close(code=code)
    except Exception:  # noqa: BLE001, S110 - the socket may already be closed; nothing to do
        pass


async def _push_one(path: Path, hub: Hub, socket: _Socket) -> None:
    """Catch one socket up after a new message; close it if its user is no longer a side."""
    try:
        await _catch_up(path, socket)
    except NotFound:
        # The relationship or the account is gone: nothing reaches this side any more.
        hub.remove(socket)
        _log_connection("closed", "access")
        await _close(socket.websocket, config.CHAT_CLOSE_REFUSED)
    except Exception as exc:  # noqa: BLE001 - one broken socket must not stop the others
        hub.remove(socket)
        logger.warning("chat_error", extra={"diagnostic": llm.error_diagnostic(exc)})
        await _close(socket.websocket, config.CHAT_CLOSE_ERROR)


async def _notify(path: Path, hub: Hub, thread_id: int, sender_id: str) -> None:
    """Tell the other side's sockets on other threads that this thread has a new message."""
    checked: dict[str, bool] = {}
    for socket in hub.elsewhere(thread_id, sender_id):
        if socket.user_id not in checked:
            # The store's read is the check that this user is a side of the thread. A failure is
            # this user's alone: the message is stored and pushed, so the sender's socket and the
            # other users' notifications go on.
            try:
                await _in_thread(
                    path,
                    lambda conn, user=socket.user_id: messages.list_messages(
                        conn, user, thread_id, limit=1
                    ),
                )
                checked[socket.user_id] = True
            except NotFound:
                checked[socket.user_id] = False
            except Exception as exc:  # noqa: BLE001 - e.g. the store busy past its timeout
                checked[socket.user_id] = False
                logger.warning("chat_error", extra={"diagnostic": llm.error_diagnostic(exc)})
        if checked[socket.user_id]:
            payload = {"type": "notification", "kind": "message_received", "thread": thread_id}
            try:
                async with socket.lock:
                    await _send_json(socket, payload)
            except Exception as exc:  # noqa: BLE001 - one broken socket must not stop the others
                hub.remove(socket)
                logger.warning("chat_error", extra={"diagnostic": llm.error_diagnostic(exc)})
                await _close(socket.websocket, config.CHAT_CLOSE_ERROR)


async def _not_sent(socket: _Socket) -> None:
    """Tell the sender their message was not stored: the fixed error, never the reason."""
    async with socket.lock:
        await _send_json(socket, {"type": "error", "code": config.CHAT_ERROR_NOT_SENT})


async def _send(path: Path, hub: Hub, socket: _Socket, frame: dict) -> None:
    """Store a message from this socket's user and push it; a refusal gets the fixed error."""
    if set(frame) != {"type", "text"}:
        raise _Refused("frame")
    text = frame["text"]
    try:
        await _in_thread(
            path,
            lambda conn: messages.send_message(conn, socket.user_id, socket.thread_id, text),
        )
    except NotFound, values.StoreValueError:
        # Ended, deleted, empty or too long: the sender learns only that it was not sent.
        logger.info("chat_message", extra={"status": "refused"})
        await _not_sent(socket)
        return
    except (sqlite3.Error, db.StoreError) as exc:
        # The store failed (busy past its timeout, or unavailable): the transaction rolled back, so
        # "not sent" is true, and the page puts the text back (kept if the store is back by the
        # fragment's rerun). The socket stays open.
        logger.warning("chat_error", extra={"diagnostic": llm.error_diagnostic(exc)})
        await _not_sent(socket)
        return
    logger.info("chat_message", extra={"status": "sent"})
    for receiver in hub.on_thread(socket.thread_id):
        await _push_one(path, hub, receiver)
    await _notify(path, hub, socket.thread_id, socket.user_id)


async def _first_token(websocket: WebSocket, secret: str) -> _Socket:
    """Read and verify the first frame's token; return the socket's state, else _Refused."""
    text = await _receive(websocket, config.CHAT_AUTH_WAIT_SECONDS)
    if text is None:
        raise _Refused("timeout")
    claims, after_id = _auth(_parse(text), secret)
    return _Socket(websocket, claims.user_id, claims.thread_id, claims.expires_at, after_id)


async def _renew(path: Path, socket: _Socket, frame: dict, secret: str) -> None:
    """Take a new token on an open socket: the same user and thread only, then catch up."""
    claims, after_id = _auth(frame, secret)
    if (claims.user_id, claims.thread_id) != (socket.user_id, socket.thread_id):
        raise _Refused("renewal")
    socket.expires_at = claims.expires_at
    try:
        await _catch_up(path, socket, after_id)
    except NotFound:
        raise _Refused("access") from None
    await _ready(socket)


async def _serve(
    path: Path, hub: Hub, websocket: WebSocket, allowed_origins: frozenset[str]
) -> None:
    """Check the handshake and the token, then relay frames until the socket closes or expires."""
    origin = websocket.headers.get("origin")
    if origin not in allowed_origins or websocket.scope.get("query_string"):
        # Refused before the handshake completes; the browser sees a failed connection.
        _log_connection("refused", "origin" if origin not in allowed_origins else "url")
        await websocket.close(code=config.CHAT_CLOSE_REFUSED)
        return
    secret = config.chat_token_secret()
    if secret is None:
        _log_connection("refused", "no_secret")
        await websocket.close(code=config.CHAT_CLOSE_REFUSED)
        return
    await websocket.accept()
    socket = None
    try:
        socket = await _first_token(websocket, secret)
        # In the hub before its catch-up: a message stored while the catch-up reads is then pushed
        # to it (after the catch-up, under its lock), never missed. A push to a socket whose user
        # is not a side of its thread finds nothing: the push's own read refuses it.
        hub.add(socket)
        try:
            await _catch_up(path, socket)
        except NotFound:
            raise _Refused("access") from None
        await _ready(socket)
        _log_connection("accepted")
        while True:
            text = await _receive(websocket, socket.expires_at - time.time())
            if text is None:
                raise _Refused("expired")
            frame = _parse(text)
            if frame["type"] == "auth":
                await _renew(path, socket, frame, secret)
            else:
                await _send(path, hub, socket, frame)
    except _Refused as refused:
        _log_connection("refused", refused.args[0])
        await _close(websocket, config.CHAT_CLOSE_REFUSED)
    finally:
        if socket is not None:
            hub.remove(socket)


def create_app(
    store_path: Callable[[], Path], allowed_origins: Callable[[], frozenset[str]]
) -> FastAPI:
    """Return the chat app: it uses the store `store_path()` names, for these origins."""
    # Both are read for each socket: in demo mode the store is the page's temporary one, made on
    # first use, and the allowed origins follow the port Streamlit is serving.
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, telemetry=_NO_TELEMETRY)
    hub = Hub()
    app.state.hub = hub

    @app.websocket(config.CHAT_SOCKET_PATH)
    async def chat_socket(websocket: WebSocket) -> None:
        """Serve one socket; any error that reaches here is logged by diagnostic and closes it."""
        try:
            path = await to_thread.run_sync(store_path)
            await _serve(path, hub, websocket, allowed_origins())
        except WebSocketDisconnect:
            _log_connection("closed")
        except Exception as exc:  # noqa: BLE001 - uvicorn would log the traceback, which may quote
            logger.warning("chat_error", extra={"diagnostic": llm.error_diagnostic(exc)})
            await _close(websocket, config.CHAT_CLOSE_ERROR)

    return app
