"""The Messages page (T11.4b, PRD feature 30, AC-45): a coach-client conversation in real time.

Each side of a relationship reads its thread (also after the end) through `src/store/messages.py`.
The thread is drawn by a browser component (`views/components/messages.mjs`, `st.components.v2`)
inside an `st.fragment`. With the chat socket mounted (`streamlit run serve.py`) and an active
relationship, each run of the fragment mints a token for the acting user from `views/account.py`
(never from anything the browser sends) and hands it to the component in its `data` only; the
component keeps the socket and, before the token expires, triggers a rerun of the fragment alone
(not the page, so nothing else runs on a timer). Its `key` is fixed per thread, so a new token
updates the component instead of mounting a new one. Without the socket (`streamlit run app.py`),
or on a page opened at an address the socket refuses, the thread is read-only and the page says so.
Under a gymer's active thread, `views/drafts.py` offers consent (a) and AI drafts of log entries
from the gymer's own messages (T11.5); with an ended thread or none, it shows the consent with its
withdraw button only, while it is given. Above it, `views/coach_ai_consent.py` offers consent (b)
with a switch per use of the coach's AI (T11.6a), under the active thread only.
"""

from pathlib import Path

import streamlit as st

from src import account as accounts
from src import chat, config
from src.realtime import page as realtime_page
from src.realtime import server as realtime_server
from src.store import messages, users
from src.store.access import NotFound
from views import account, coach_ai_consent, drafts, header
from views.text import lang, t

URL_PATH = "messages"
THREAD_KEY = "messages_thread"
ROLES = ("coach", "gymer")
_HERE = Path(__file__).parent / "components"
# The component's root; the JavaScript fills it with text only.
_HTML = """
<div class="fk-messages">
  <div class="fk-list" role="log" aria-live="polite"></div>
  <p class="fk-status" aria-live="polite"></p>
  <p class="fk-notice" role="status"></p>
  <div class="fk-form" hidden>
    <textarea class="fk-input" rows="3"></textarea>
    <button class="fk-send" type="button"></button>
  </div>
</div>
"""
# Registered once, at import: our own JavaScript and CSS, read from the repo, never user text.
_COMPONENT = st.components.v2.component(
    "fitkompass_messages",
    html=_HTML,
    css=(_HERE / "messages.css").read_text(encoding="utf-8"),
    js=(_HERE / "messages.mjs").read_text(encoding="utf-8"),
)
# The texts the component shows, by the name it uses.
_LABELS = (
    "send",
    "placeholder",
    "you",
    "empty",
    "connecting",
    "live",
    "stopped",
    "not_sent",
    "too_long",
    "other_thread",
)


def component_key(thread_id: int) -> str:
    """Return the component's key for a thread: fixed, so a new token never remounts it."""
    return f"messages_component_{thread_id}"


def _threads(user_id: str) -> list[dict] | None:
    """Return the user's relationships, active first then newest; None if the store failed."""
    try:
        with accounts.open_store(account.store_path()) as conn:
            found = users.list_relationships(conn, user_id)
    except accounts.StoreUnavailable:
        return None
    except NotFound:
        return []  # deleted in another tab: the next run shows the start page
    return sorted(found, key=lambda row: (row["status"] != "active", -row["id"]))


def _label(thread: dict) -> str:
    """Return a thread's name in the picker: the other side, marked when the relationship ended."""
    if thread["status"] == "active":
        return thread["other_name"]
    return t("messages.ended_suffix", name=thread["other_name"])


def _pick(threads: list[dict]) -> dict:
    """Return the thread to show: the picker's choice when there are several, else the only one."""
    if len(threads) == 1:
        name = chat.escape_markdown(threads[0]["other_name"])
        st.markdown(f"**{t('messages.with', name=name)}**")
        return threads[0]
    by_id = {thread["id"]: thread for thread in threads}
    # The labels in today's language now: Streamlit (and AppTest) may call format_func outside the
    # run, where the session's language cannot be read.
    labels = {thread_id: _label(thread) for thread_id, thread in by_id.items()}
    if st.session_state.get(THREAD_KEY) not in by_id:
        st.session_state[THREAD_KEY] = threads[0]["id"]
    chosen = st.selectbox(
        t("messages.pick"), options=list(by_id), format_func=labels.__getitem__, key=THREAD_KEY
    )
    return by_id[chosen]


def _socket(user_id: str, thread_id: int) -> tuple[dict | None, str | None]:
    """Return the socket's data with a new token, or None and the note saying why there is none."""
    if not realtime_server.mounted():
        return None, t("messages.realtime_off")
    port = realtime_server.serving_port()
    if not realtime_page.page_may_connect(st.context.url, port):
        address = f"http://localhost:{port}"
        return None, t("messages.wrong_address", address=address)
    found = realtime_page.socket_data(user_id, thread_id)
    if found is None:
        return None, t("messages.realtime_off")
    return found, None


@st.fragment
def _thread(user_id: str, thread_id: int) -> None:
    """Show the thread in the component; rerun alone when the component asks for a new token."""
    # The relationship is read again on every run, the fragment's own included: a renewal after the
    # other side ended it then gets no token, and the thread turns read-only without a page rerun.
    try:
        with accounts.open_store(account.store_path()) as conn:
            rows = messages.list_messages(conn, user_id, thread_id)
            found = [
                row for row in users.list_relationships(conn, user_id) if row["id"] == thread_id
            ]
    except accounts.StoreUnavailable:
        st.error(t("account.store_unavailable"), icon=":material/error:")
        return
    except NotFound:
        return  # the relationship or the account was deleted in another tab
    if not found:
        return
    active = found[0]["status"] == "active"
    if not active:
        st.info(t("messages.ended"), icon=":material/lock:")
    socket, note = _socket(user_id, thread_id) if active else (None, None)
    if note is not None:
        st.caption(f":material/sync_disabled: {note}")
    _COMPONENT(
        key=component_key(thread_id),
        data={
            "messages": realtime_page.items(rows, user_id),
            "socket": socket,
            "can_send": socket is not None,
            "max_chars": config.MESSAGE_MAX_CHARS,
            "other_name": found[0]["other_name"],
            "locale": lang(),
            "labels": {name: t(f"messages.{name}") for name in _LABELS},
        },
        on_renew_change=lambda: None,
    )


def page() -> None:
    """Show the Messages page: the intro, the conversation picker and the thread."""
    with header.main_column():
        header.show()
        account.store_notice()
        user = account.current_user()
        if user is None or user["role"] not in ROLES:
            return  # not registered for them (views/navigation.py); never reached
        st.subheader(t("page.messages"))
        st.markdown(t(f"messages.intro_{user['role']}"))
        st.caption(f":material/science: {t('messages.made_up_only')}")
        threads = _threads(user["id"])
        if threads is None:
            st.error(t("account.store_unavailable"), icon=":material/error:")
            return
        if not threads:
            st.caption(t(f"messages.none_{user['role']}"))
            if user["role"] == "gymer":
                drafts.standing_consent(user["id"])  # withdrawable with no conversation too
            return
        thread = _pick(threads)
        _thread(user["id"], thread["id"])
        if user["role"] == "gymer":
            # Outside the thread's fragment: a renewal reruns the fragment alone, never a draft.
            coach_ai_consent.section(user["id"], thread)
            drafts.section(user["id"], thread)
