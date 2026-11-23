"""Tests for the chat server's token and its secret (T11.4a, D24): mint, verify, refuse."""

import ast
import base64
import json
from pathlib import Path

import pytest

from src import config
from src.config import environment as config_environment
from src.realtime import tokens
from src.realtime.tokens import TokenRefused

ROOT = Path(__file__).resolve().parent.parent
# Obvious test secrets, never a real one.
SECRET = "test-chat-secret-" + "x" * 32
OTHER_SECRET = "test-other-secret-" + "y" * 32
USER = "a" * 64
OTHER_USER = "b" * 64
THREAD = 7
NOW = 1_800_000_000.0


def _b64(data: bytes) -> str:
    """Return base64url text without padding, as the token writes it."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _forge(payload: object, secret: str = SECRET) -> str:
    """Return a token with any payload, correctly signed, to test the payload's checks."""
    signed = f"v1.{_b64(json.dumps(payload).encode('utf-8'))}"
    return f"{signed}.{_b64(tokens._signature(signed, secret))}"


# --- Mint and verify -----------------------------------------------------------------------------


def test_a_minted_token_verifies_to_its_user_thread_and_expiry():
    """The token carries the user, the thread and an expiry TTL seconds after minting."""
    token = tokens.mint(USER, THREAD, SECRET, now=NOW)
    claims = tokens.verify(token, SECRET, now=NOW + 1)
    assert claims == tokens.Claims(USER, THREAD, int(NOW) + config.CHAT_TOKEN_TTL_SECONDS)


def test_the_token_holds_only_the_user_the_thread_and_the_expiry():
    """The payload has exactly three fields: no name, email, role or anything else."""
    token = tokens.mint(USER, THREAD, SECRET, now=NOW)
    payload = json.loads(tokens._decode(token.split(".")[1]))
    assert payload == {"u": USER, "t": THREAD, "e": int(NOW) + config.CHAT_TOKEN_TTL_SECONDS}


def test_the_lifetime_is_fifteen_minutes_and_patchable(monkeypatch):
    """15 minutes by default; read at call time, so a test (T11.4b's too) can shorten it."""
    assert config.CHAT_TOKEN_TTL_SECONDS == 15 * 60
    monkeypatch.setattr(config, "CHAT_TOKEN_TTL_SECONDS", 2)
    token = tokens.mint(USER, THREAD, SECRET, now=NOW)
    assert tokens.verify(token, SECRET, now=NOW + 1).expires_at == int(NOW) + 2
    with pytest.raises(TokenRefused):
        tokens.verify(token, SECRET, now=NOW + 2)


@pytest.mark.parametrize("offset", [config.CHAT_TOKEN_TTL_SECONDS, 10**6])
def test_an_expired_token_is_refused(offset):
    """At its expiry or later, a token is refused."""
    token = tokens.mint(USER, THREAD, SECRET, now=NOW)
    with pytest.raises(TokenRefused):
        tokens.verify(token, SECRET, now=NOW + offset)


def test_a_token_minted_for_one_user_never_verifies_as_another():
    """Swapping the user (or the thread) in the payload breaks the signature."""
    token = tokens.mint(USER, THREAD, SECRET, now=NOW)
    version, _body, signature = token.split(".")
    for payload in (
        {"u": OTHER_USER, "t": THREAD, "e": int(NOW) + 60},
        {"u": USER, "t": THREAD + 1, "e": int(NOW) + 60},
    ):
        body = _b64(json.dumps(payload).encode("utf-8"))
        with pytest.raises(TokenRefused):
            tokens.verify(f"{version}.{body}.{signature}", SECRET, now=NOW)


@pytest.mark.parametrize(
    "token",
    [
        None,
        42,
        b"bytes",
        "",
        "v1",
        "v1..",
        "v1.a.b.c",
        "v2.e30.AAAA",
        "v1.!!!.@@@",
        "v1.e30.é",
        "x" * 2000,
    ],
)
def test_a_malformed_token_is_refused(token):
    """Anything that is not a well-formed token is refused, never an unexpected error."""
    with pytest.raises(TokenRefused):
        tokens.verify(token, SECRET, now=NOW)


def test_a_token_signed_with_another_secret_is_refused():
    """A token signed under another secret is refused (a bad signature)."""
    token = tokens.mint(USER, THREAD, OTHER_SECRET, now=NOW)
    with pytest.raises(TokenRefused):
        tokens.verify(token, SECRET, now=NOW)


def test_a_cut_signature_is_refused():
    """A truncated signature does not verify."""
    token = tokens.mint(USER, THREAD, SECRET, now=NOW)
    with pytest.raises(TokenRefused):
        tokens.verify(token[:-4], SECRET, now=NOW)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        "text",
        {"u": USER, "t": THREAD},
        {"u": USER, "t": THREAD, "e": int(NOW) + 60, "role": "coach"},
        {"u": "", "t": THREAD, "e": int(NOW) + 60},
        {"u": "x" * 500, "t": THREAD, "e": int(NOW) + 60},
        {"u": "ü" * 4, "t": THREAD, "e": int(NOW) + 60},
        {"u": 5, "t": THREAD, "e": int(NOW) + 60},
        {"u": USER, "t": 0, "e": int(NOW) + 60},
        {"u": USER, "t": True, "e": int(NOW) + 60},
        {"u": USER, "t": "7", "e": int(NOW) + 60},
        {"u": USER, "t": THREAD, "e": "later"},
        {"u": USER, "t": THREAD, "e": True},
        {"u": USER, "t": THREAD, "e": float(NOW) + 60},
        # Signed, but living longer than any token minted now could.
        {"u": USER, "t": THREAD, "e": int(NOW) + config.CHAT_TOKEN_TTL_SECONDS + 3600},
    ],
)
def test_a_signed_token_with_a_wrong_payload_is_refused(payload):
    """The payload's form is checked too: exact fields, their types, and a lifetime in range."""
    with pytest.raises(TokenRefused):
        tokens.verify(_forge(payload), SECRET, now=NOW)


def test_an_empty_secret_refuses_every_token_and_mints_none():
    """Without a secret nothing is minted and nothing verifies."""
    token = tokens.mint(USER, THREAD, SECRET, now=NOW)
    with pytest.raises(TokenRefused):
        tokens.verify(token, "", now=NOW)
    with pytest.raises(ValueError):
        tokens.mint(USER, THREAD, "", now=NOW)


@pytest.mark.parametrize("user, thread", [("", THREAD), (USER, 0), (USER, True), (5, THREAD)])
def test_mint_refuses_a_bad_user_or_thread_without_naming_it(user, thread):
    """A bad argument is a ValueError whose message holds no value."""
    with pytest.raises(ValueError) as error:
        tokens.mint(user, thread, SECRET, now=NOW)
    assert USER not in str(error.value)


def test_a_refusal_never_quotes_the_token():
    """TokenRefused carries no message, so a traceback or a log cannot quote the token."""
    token = tokens.mint(USER, THREAD, SECRET, now=NOW)
    with pytest.raises(TokenRefused) as error:
        tokens.verify(token, SECRET, now=NOW + 10**6)
    assert str(error.value) == "" and error.value.args == ()


# --- The secret ----------------------------------------------------------------------------------


@pytest.fixture
def no_env_secret(monkeypatch):
    """Remove the chat secret's environment variable so a test sees only what it sets."""
    monkeypatch.delenv(config.CHAT_TOKEN_SECRET_ENV_NAME, raising=False)


def test_the_secret_is_read_from_its_secrets_section(secrets_from_file, no_env_secret):
    """[chat] token_secret in secrets.toml is the secret."""
    secrets_from_file(f'[chat]\ntoken_secret = "{SECRET}"\n')
    assert config.chat_token_secret() == SECRET


def test_the_secret_falls_back_to_the_environment(secrets_from_file, monkeypatch):
    """Without the section, the environment variable is the secret."""
    secrets_from_file('OPENROUTER_API_KEY = "sk-test-not-a-real-key"\n')
    monkeypatch.setenv(config.CHAT_TOKEN_SECRET_ENV_NAME, SECRET)
    assert config.chat_token_secret() == SECRET


@pytest.mark.parametrize(
    "text",
    [
        "",
        '[chat]\ntoken_secret = "short"\n',
        f'[chat]\ntoken_secret = "{config.CHAT_TOKEN_SECRET_PLACEHOLDER}"\n',
        "[chat]\ntoken_secret = 12345\n",
        f'token_secret = "{SECRET}"\n',
        "this is not toml [",
    ],
)
def test_a_missing_short_placeholder_or_broken_secret_is_none(
    secrets_from_file, no_env_secret, text
):
    """No usable secret reads as None, so no token is minted or accepted."""
    secrets_from_file(text)
    assert config.chat_token_secret() is None


def test_the_example_s_placeholder_is_the_one_config_refuses():
    """The example secrets file names the section with the placeholder config treats as unset."""
    example = (ROOT / ".streamlit" / "secrets.toml.example").read_text(encoding="utf-8")
    assert "# [chat]" in example
    assert f'# token_secret = "{config.CHAT_TOKEN_SECRET_PLACEHOLDER}"' in example


# The secret's names, which only src/config/environment.py may spell out.
_SECRET_NAMES = {
    config.CHAT_TOKEN_SECRET_ENV_NAME,
    config.CHAT_TOKEN_SECRET_NAME,
    config.CHAT_TOKEN_SECRET_PLACEHOLDER,
}
_SCANNED = [*(ROOT / "src").rglob("*.py"), *(ROOT / "views").rglob("*.py")]
_SCANNED += [ROOT / "app.py", ROOT / "serve.py"]
_SCANNED += sorted((ROOT / "scripts").glob("*.py"))


def _reads_the_secret(node: ast.AST) -> bool:
    """Return True for a use of the reader: `.chat_token_secret`, the bare name, or its import."""
    if isinstance(node, ast.Attribute):
        return node.attr == "chat_token_secret"
    if isinstance(node, ast.Name):
        return node.id == "chat_token_secret"
    if isinstance(node, ast.ImportFrom):
        return any(alias.name == "chat_token_secret" for alias in node.names)
    return False


def test_only_the_config_function_reads_the_secret():
    """No other module names the secret's key or variable; only the socket and the page read it."""
    environment = ROOT / "src" / "config" / "environment.py"
    named, callers = [], []
    for path in _SCANNED:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        relative = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value in _SECRET_NAMES:
                if path != environment:
                    named.append(relative)
            if _reads_the_secret(node):
                callers.append(relative)
    assert named == []
    # The socket verifies with it, and the Messages page's helper mints with it (T11.4b).
    assert set(callers) == {"src/realtime/app.py", "src/realtime/page.py"}


def test_the_callers_scan_sees_an_import_and_a_bare_name():
    """`from src.config import chat_token_secret` and a call by name are found, not only `.attr`."""
    tree = ast.parse("from src.config import chat_token_secret\nchat_token_secret()\n")
    found = {type(node).__name__ for node in ast.walk(tree) if _reads_the_secret(node)}
    assert found == {"ImportFrom", "Name"}


def test_the_reader_is_the_one_in_environment():
    """config.chat_token_secret is environment's function, so a patch reaches every caller."""
    assert config.chat_token_secret is config_environment.chat_token_secret
