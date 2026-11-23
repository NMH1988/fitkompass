"""The chat socket's signed, short-lived token (T11.4a, D24).

The Streamlit page mints a token on each run for the acting user (worked out from `st.user`, or the
demo picker's closed list) and one thread; the browser sends it as the socket's first message, and
a token that verifies is the server's only source of the acting user. It holds only the keyed user
ID, the thread and the expiry, signed with HMAC-SHA256 under `config.chat_token_secret()`. It is not
encrypted: the user ID in it is the keyed hash, never a Google name, email or picture.

Format: `v1.<payload>.<signature>`, both parts base64url without padding, the payload compact JSON.
Every way a token can fail gives the same `TokenRefused`, with no message, so an error never quotes
the token or says which check failed.
"""

import base64
import binascii
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from src import config

_VERSION = "v1"
_FIELDS = frozenset({"u", "t", "e"})


class TokenRefused(Exception):  # noqa: N818 - a refusal, not a program error
    """Raised for every token that does not verify: malformed, forged, expired or too long-lived."""


@dataclass(frozen=True)
class Claims:
    """What a verified token says: the acting user, the thread and when the token expires."""

    user_id: str
    thread_id: int
    expires_at: int


def _encode(data: bytes) -> str:
    """Return base64url text without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(text: str) -> bytes:
    """Return the bytes of base64url text without padding; TokenRefused if it is not that."""
    if not text or not text.isascii():
        raise TokenRefused
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except binascii.Error, ValueError:
        raise TokenRefused from None


def _signature(signed: str, secret: str) -> bytes:
    """Return the HMAC-SHA256 of the signed part under the secret."""
    return hmac.new(secret.encode("utf-8"), signed.encode("ascii"), hashlib.sha256).digest()


def _valid_user_id(value: object) -> bool:
    """Return True for a user ID the store could hold: printable ASCII, not too long."""
    return (
        isinstance(value, str)
        and 0 < len(value) <= config.STORE_ID_MAX_CHARS
        and value.isascii()
        and value.isprintable()
    )


def _valid_thread_id(value: object) -> bool:
    """Return True for a positive integer row ID (a boolean is not one)."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def mint(user_id: str, thread_id: int, secret: str, *, now: float | None = None) -> str:
    """Return a token for this user and thread that expires after config.CHAT_TOKEN_TTL_SECONDS."""
    if not secret:
        raise ValueError("chat token secret is not set")
    if not _valid_user_id(user_id) or not _valid_thread_id(thread_id):
        raise ValueError("chat token: invalid user or thread")  # names no value
    issued = int(time.time() if now is None else now)
    payload = {"u": user_id, "t": thread_id, "e": issued + config.CHAT_TOKEN_TTL_SECONDS}
    body = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signed = f"{_VERSION}.{body}"
    return f"{signed}.{_encode(_signature(signed, secret))}"


def verify(token: object, secret: str, *, now: float | None = None) -> Claims:
    """Return the token's claims if its signature, form and expiry hold; else TokenRefused."""
    if not secret or not isinstance(token, str) or len(token) > config.CHAT_TOKEN_MAX_CHARS:
        raise TokenRefused
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != _VERSION:
        raise TokenRefused
    signed = f"{parts[0]}.{parts[1]}"
    # The signature is checked before the payload is parsed, in constant time.
    if not hmac.compare_digest(_decode(parts[2]), _signature(signed, secret)):
        raise TokenRefused
    try:
        payload = json.loads(_decode(parts[1]))
    except UnicodeDecodeError, json.JSONDecodeError:
        raise TokenRefused from None
    if not isinstance(payload, dict) or set(payload) != _FIELDS:
        raise TokenRefused
    user_id, thread_id, expires_at = payload["u"], payload["t"], payload["e"]
    if not _valid_user_id(user_id) or not _valid_thread_id(thread_id):
        raise TokenRefused
    if not isinstance(expires_at, int) or isinstance(expires_at, bool):
        raise TokenRefused
    current = time.time() if now is None else now
    # Expired, or living longer than a token minted now could (a token from another setting).
    if (
        current >= expires_at
        or expires_at > current + config.CHAT_TOKEN_TTL_SECONDS + config.CHAT_TOKEN_SKEW_SECONDS
    ):
        raise TokenRefused
    return Claims(user_id=user_id, thread_id=thread_id, expires_at=expires_at)
