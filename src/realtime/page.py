"""What the Messages page hands its browser component (T11.4b, D24): the thread and a fresh token.

The page reads the thread from the store and, on every run of the thread's fragment, mints a token
for the acting user it worked out from `st.user` or the demo picker (`views/account.py`), never from
anything the browser sends. The token goes to the component's `data` only: never into a URL,
`st.query_params`, `st.session_state` or a log. This module imports no streamlit.
"""

import time
from urllib.parse import urlsplit

from src import config
from src.realtime import tokens


def items(rows: list[dict], user_id: str) -> list[dict]:
    """Return messages as the browser gets them: `mine` instead of the sender's ID."""
    return [
        {
            "id": row["id"],
            "mine": row["sender_id"] == user_id,
            "text": row["text"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def allowed_origins(port: int) -> frozenset[str]:
    """Return the origins allowed to open a socket: the local hosts on this port, and public."""
    local = {f"http://{host}:{port}" for host in config.CHAT_LOCAL_HOSTS}
    return frozenset(local) | config.CHAT_PUBLIC_ORIGINS


def origin_of(url: str) -> str | None:
    """Return a URL's origin (scheme, host, and port when it has one), or None if it has none."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if not parts.scheme or not parts.hostname:
        return None
    host = parts.hostname
    return f"{parts.scheme}://{host}" if port is None else f"{parts.scheme}://{host}:{port}"


def page_may_connect(page_url: str | None, port: int) -> bool:
    """Return True if a page at this URL may open the socket; an unknown URL (no browser) may."""
    # A browser always gives its URL (st.context.url); AppTest gives none. A page opened at another
    # host or port would be refused by the socket's origin check, so it is told so instead.
    return page_url is None or origin_of(page_url) in allowed_origins(port)


def socket_data(user_id: str, thread_id: int, *, now: float | None = None) -> dict | None:
    """Return the socket's settings with a new token for this user and thread; None if no secret."""
    secret = config.chat_token_secret()
    if secret is None:
        return None
    issued = time.time() if now is None else now
    token = tokens.mint(user_id, thread_id, secret, now=issued)
    return {
        "path": config.CHAT_MOUNT_PATH + config.CHAT_SOCKET_PATH,
        "token": token,
        # Seconds, counted from when the browser gets the data: the component keeps its own clock.
        "expires_in": config.CHAT_TOKEN_TTL_SECONDS,
        "renew_before": config.CHAT_TOKEN_RENEW_BEFORE_SECONDS,
        "renew_retry": config.CHAT_RENEW_RETRY_SECONDS,
        "reconnect_first": config.CHAT_RECONNECT_FIRST_SECONDS,
        "reconnect_max": config.CHAT_RECONNECT_MAX_SECONDS,
        "max_refusals": config.CHAT_RECONNECT_MAX_REFUSALS,
        "refused_code": config.CHAT_CLOSE_REFUSED,
    }
