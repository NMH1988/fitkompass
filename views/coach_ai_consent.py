"""A gymer's consent (b) on the Messages page (T11.6a): their coach's AI and their conversation.

Under the gymer's active thread: consent (b)'s common text, naming the current coach, then each use
built so far (`src/coach_thread.py`) with its own text, whether it is on, and one button to switch
it on or off. Each use is its own row in `ai_consents`, so switching one leaves the others as they
are; a use switched on under an older text counts as off and asks again, with a button to switch
it off too. Consent (b) belongs to one relationship, so an ended thread shows none of it: it is no
consent any more (`ai_consents`) and the coach's AI reads nothing of it.
"""

import streamlit as st

from src import account as accounts
from src import chat, coach_thread
from src.store import ai_consents
from src.store.access import NotFound
from views import account
from views.text import lang, t

FLASH_KEY = "coach_ai_flash"


def _set(user_id: str, thread_id: int, use: str, *, on: bool) -> None:
    """Switch one use of consent (b) on (to its current text) or off, then rerun."""
    try:
        with accounts.open_store(account.store_path()) as conn:
            if on:
                version = coach_thread.use_version(use)
                ai_consents.give(conn, user_id, coach_thread.PURPOSE, version, thread_id, use)
            else:
                ai_consents.withdraw(conn, user_id, coach_thread.PURPOSE, thread_id, use)
    except accounts.StoreUnavailable, NotFound:
        # NotFound: the relationship ended in the meantime; the next run shows the thread ended.
        st.error(t("account.store_unavailable"), icon=":material/error:")
        return
    st.session_state[FLASH_KEY] = "coach_ai.turned_on" if on else "coach_ai.turned_off"
    st.rerun()


def _use(user_id: str, thread_id: int, coach: str, use: str, current: dict | None) -> None:
    """Show one use: its text, whether it is on, and its one-click switch."""
    on = current is not None and current["text_version"] == coach_thread.use_version(use)
    text_column, switch_column = st.columns([4, 1], vertical_alignment="center")
    # The coach's name is a user's own text: escaped, so it never reads as Markdown or a link.
    text_column.markdown(coach_thread.use_text(lang(), chat.escape_markdown(coach), use))
    state = t("coach_ai.on") if on else t("coach_ai.off")
    switch_column.caption(state)
    key = f"coach_ai_{use}_{thread_id}"
    if on:
        if switch_column.button(t("coach_ai.turn_off"), key=key):
            _set(user_id, thread_id, use, on=False)
        return
    if current is not None:
        st.warning(t("coach_ai.changed"), icon=":material/update:")
        if st.button(t("coach_ai.turn_off"), key=f"{key}_older"):
            _set(user_id, thread_id, use, on=False)
    if switch_column.button(t("coach_ai.turn_on"), key=key, type="primary"):
        _set(user_id, thread_id, use, on=True)


def section(user_id: str, thread: dict) -> None:
    """Show consent (b) with a switch per use under the gymer's active thread; none when ended."""
    if thread["status"] != "active":
        return
    uses = tuple(coach_thread.USE_TEXT_KEYS)
    try:
        with accounts.open_store(account.store_path()) as conn:
            current = {
                use: ai_consents.current(conn, user_id, coach_thread.PURPOSE, thread["id"], use)
                for use in uses
            }
    except accounts.StoreUnavailable:
        st.error(t("account.store_unavailable"), icon=":material/error:")
        return
    except NotFound:
        return  # ended in another tab: the next run shows the thread ended
    st.divider()
    st.markdown(f"**{t('coach_ai.title')}**")
    flash = st.session_state.pop(FLASH_KEY, None)
    if flash is not None:
        st.info(t(flash))
    coach = thread["other_name"]
    st.caption(coach_thread.intro_text(lang(), chat.escape_markdown(coach)))
    for use in uses:
        _use(user_id, thread["id"], coach, use, current[use])
