"""A gymer's AI drafts of log entries from a photo or a voice note, on the Today page (T11.10).

Consent (c) is given or withdrawn here in one click, with its text (`src/media.py`); a consent to
an older text counts as none and asks again. Only with it does the gymer see the choice of a
source: upload a photo, take one (the camera opens only once they choose it, never on a page load)
or record a voice note, each under the warning to keep other people, documents and labels out and
to record only their own voice. The file is checked and cleaned in memory (`media.clean_photo()`,
`media.clean_voice()`) before anything is sent; only on the gymer's press does
`src/agent/media_drafts.py` send it, and the cards that come back say they were drafted by an AI
model and wait for the gymer's decision. After a press the widgets get new keys, so the next run of
the page starts empty and the file is not sent twice. The run lives in this session only
(`MediaDrafter`), keyed by the acting user.
"""

from datetime import date

import streamlit as st

from src import account as accounts
from src import chat, config, guard, i18n, media
from src.agent import graph
from src.agent import media_drafts as workflow
from src.store import ai_consents
from src.store.access import NotFound
from views import account, drafts, resources
from views.text import label_of, lang, t

FLASH_KEY = "media_flash"
SOURCE_KEY = "media_source"
# Bumped after each press, so the widgets start empty and the file is not sent twice.
ROUND_KEY = "media_round"
# Set by a press: the next run clears the source choice before its widget is drawn.
RESET_KEY = "media_reset"
SOURCES = ("upload", "camera", "voice")


def _drafter(user_id: str) -> workflow.MediaDrafter:
    """Return the session's runs of this user (demo mode can switch users)."""
    key = f"media_drafter_{user_id}"
    if key not in st.session_state:
        st.session_state[key] = workflow.MediaDrafter()
    return st.session_state[key]


def _prompt_path(kind: media.Kind):
    """Return the path of the owner's fixed instruction for this kind of file."""
    return config.PHOTO_PROMPT_PATH if kind == "photo" else config.VOICE_PROMPT_PATH


def _context(
    kind: media.Kind, file: bytes = b"", drafter: workflow.MediaDrafter | None = None
) -> workflow.MediaContext:
    """Return a run's context: the store, the file, the cached models and the instructions."""
    # A new run reads both instruction files; a decision passes the ones its run started with.
    if drafter is not None and drafter.media_prompt and drafter.draft_prompt:
        media_prompt, draft_prompt = drafter.media_prompt, drafter.draft_prompt
    else:
        media_prompt = graph.load_prompt(
            _prompt_path(kind), config.MEDIA_PROMPT_MISSING_MESSAGE, "prompt.media_missing"
        )
        draft_prompt = graph.load_prompt(
            config.DRAFT_PROMPT_PATH, config.DRAFT_PROMPT_MISSING_MESSAGE, "prompt.drafts_missing"
        )
    return workflow.MediaContext(
        store_path=account.store_path(),
        media_prompt=media_prompt,
        draft_prompt=draft_prompt,
        file=file,
        media_model=lambda: resources.media_model(kind),
        chat_model=resources.draft_model,
    )


def _limits() -> dict[str, int]:
    """Return the limits the texts name, from config."""
    return {
        "mb": config.PHOTO_MAX_MB,
        "megapixels": config.PHOTO_MAX_PIXELS // 1_000_000,
        "seconds": config.VOICE_MAX_SECONDS,
    }


def _current(user_id: str) -> dict | None:
    """Return the gymer's open consent (c), or None (also when the store cannot be read)."""
    try:
        with accounts.open_store(account.store_path()) as conn:
            return ai_consents.current(conn, user_id, media.PURPOSE)
    except accounts.StoreUnavailable, NotFound:
        return None


def _consent(user_id: str) -> bool:
    """Show consent (c) with its one-click button; return whether it holds for this text."""
    current = _current(user_id)
    given = current is not None and current["text_version"] == media.consent_version()
    st.caption(media.consent_text(lang()))
    if given:
        st.caption(f":material/check_circle: {t('drafts.consent_given')}")
        if st.button(t("drafts.consent_withdraw"), key="media_withdraw"):
            _set_consent(user_id, give=False)
        return True
    if current is not None:
        st.warning(t("media.consent_changed"), icon=":material/update:")
    give, withdraw = st.columns(2)
    if give.button(t("drafts.consent_give"), key="media_give", type="primary"):
        _set_consent(user_id, give=True)
    # A consent to an older text still open is withdrawn here too, not only renewed.
    if current is not None and withdraw.button(t("drafts.consent_withdraw"), key="media_withdraw"):
        _set_consent(user_id, give=False)
    return False


def _set_consent(user_id: str, *, give: bool) -> None:
    """Give or withdraw consent (c); a withdrawal drops the pending drafts at once."""
    try:
        with accounts.open_store(account.store_path()) as conn:
            if give:
                ai_consents.give(conn, user_id, media.PURPOSE, media.consent_version())
            else:
                ai_consents.withdraw(conn, user_id, media.PURPOSE)
    except accounts.StoreUnavailable, NotFound:
        st.error(t("account.store_unavailable"), icon=":material/error:")
        return
    if not give:
        _drafter(user_id).drop()
        st.session_state[FLASH_KEY] = [("info", "media.consent_withdrawn", {})]
    st.rerun()


def standing_consent(user_id: str) -> None:
    """Show the withdraw button where no draft can run (no saved profile), if consent (c) holds."""
    # The consent is the gymer's: it can be withdrawn in one click wherever Today shows (GDPR
    # Art. 7(3)), also when the profile entries it needs were deleted since.
    if _current(user_id) is None:
        return
    st.divider()
    st.markdown(f"**{t('media.title')}**")
    if st.button(t("drafts.consent_withdraw"), key="media_withdraw_standing"):
        _set_consent(user_id, give=False)


def _flash(result: workflow.RunResult) -> None:
    """Keep a run's outcome to show on the next run of the page."""
    dropped = result.counts.get("dropped", 0)
    found: list[tuple[str, str, dict]] = []
    if result.outcome == "error":
        code = result.error_code if result.error_code in i18n.TEXT["en"] else "llm.error"
        found = [("error", code, {}), ("info", "media.error", {})]
    elif result.outcome == "nothing":
        found = [("info", "media.nothing", {})]
    elif result.outcome == "refused":
        found = [("warning", "media.refused", {})]
    elif result.outcome == "no_consent":
        found = [("warning", "media.no_consent", {})]
    elif result.outcome == "profile_first":
        found = [("warning", "diary.profile_first", {})]
    elif result.outcome == "not_found":
        found = [("warning", "media.error", {})]
    elif result.outcome == "done":
        found = [("success", "media.done", {"count": result.logged})]
    if dropped and result.outcome in ("nothing", "pending"):
        found.append(("info", "media.dropped", {"count": dropped}))
    st.session_state[FLASH_KEY] = found


def _show_flash() -> None:
    """Show the last action's outcome once, in the chosen language."""
    for kind, key, params in st.session_state.pop(FLASH_KEY, None) or ():
        getattr(st, kind)(t(key, **params))


def _press(user_id: str, kind: media.Kind, data: bytes, day: date) -> None:
    """Check and clean the file, then run the workflow up to its cards on the gymer's press."""
    # The size and type checks come first: a file they refuse reaches no model.
    try:
        cleaned = media.clean_photo(data) if kind == "photo" else media.clean_voice(data)
    except media.MediaError as exc:
        st.session_state[FLASH_KEY] = [("error", exc.code, _limits())]
        return
    try:
        context = _context(kind, cleaned)
    except chat.PromptMissingError as exc:
        st.session_state[FLASH_KEY] = [("error", exc.code, {})]
        return
    # A press spends up to two model calls, so it counts against the session's limit, as a chat
    # question and a draft from messages do; a refusal makes no call.
    refused = guard.session_limiter(st.session_state).try_acquire()
    if refused is not None:
        st.session_state[FLASH_KEY] = [
            ("warning", f"drafts.{refused.reason.value}", refused.params)
        ]
        return
    with st.spinner(t("media.working")):
        result = _drafter(user_id).start(context, user_id, kind, day)
    _flash(result)


def _cards(user_id: str, pending: workflow.RunResult) -> None:
    """Show the run's cards under the AI label and what the AI read, with a decision each."""
    kind = pending.kind or "photo"
    st.info(
        t(f"media.ai_label.{kind}", provider=media.model_provider()), icon=":material/smart_toy:"
    )
    if pending.text:
        st.markdown(f"**{t(f'media.read_as.{kind}')}**")
        st.text(pending.text)  # the model's text, shown as plain text, never as Markdown
    drafter = _drafter(user_id)
    decisions = drafts.card_form(
        user_id, pending.cards, f"media_form_{drafter.thread_id}", pending.error
    )
    if decisions is not None:
        _flash(drafter.decide(_context(kind, drafter=drafter), decisions))
        st.rerun()


def _chosen_file():
    """Show the source choice and its widget; return the kind and the file chosen, if any."""
    if st.session_state.pop(RESET_KEY, False):
        st.session_state.pop(SOURCE_KEY, None)
    # Shown above the choice and again in each widget's help, so it is there with the upload, the
    # camera and the recorder alike.
    warning = t("media.keep_out", provider=media.model_provider())
    st.warning(warning, icon=":material/visibility_off:")
    # While the app holds made-up data only, so is what a file shows or says: a staged meal, and a
    # synthetic recording instead of a real voice (`docs/TESTING.md`).
    st.caption(f":material/lock: {t('media.made_up')}")
    source = st.segmented_control(
        t("media.source"), SOURCES, format_func=label_of("media.source"), key=SOURCE_KEY
    )
    turn = st.session_state.get(ROUND_KEY, 0)
    if source == "upload":
        found = st.file_uploader(
            t("media.upload", **_limits()),
            type=list(config.PHOTO_TYPES),
            max_upload_size=config.PHOTO_MAX_MB,
            help=f"{warning} {t('media.made_up_photo')}",
            key=f"media_upload_{turn}",
        )
    elif source == "camera":
        # Drawn only once the gymer chose it, so the browser never asks for the camera on a page
        # load.
        found = st.camera_input(
            t("media.camera"),
            help=f"{warning} {t('media.made_up_photo')}",
            key=f"media_camera_{turn}",
        )
    elif source == "voice":
        found = st.audio_input(
            t("media.voice", **_limits()),
            sample_rate=config.VOICE_SAMPLE_RATE,
            help=f"{t('media.voice_help')} {warning} {t('media.made_up_voice')}",
            key=f"media_voice_{turn}",
        )
    else:
        return None, None
    return ("voice" if source == "voice" else "photo"), found


def section(user: dict, day: date) -> None:
    """Show consent (c), the source choice, the file's button and the cards on Today."""
    user_id = user["id"]
    # Before any upload widget is drawn, so no photo or recording is written to a temporary file.
    media.keep_uploads_in_memory()
    st.divider()
    st.markdown(f"**{t('media.title')}**")
    _show_flash()
    if not _consent(user_id):
        _drafter(user_id).drop()  # e.g. withdrawn in another tab: no draft is kept
        return
    pending = _drafter(user_id).pending()
    if pending is not None:
        _cards(user_id, pending)
        return
    kind, found = _chosen_file()
    if found is None:
        return
    if st.button(
        t("media.button"),
        key="media_start",
        type="primary",
        icon=":material/auto_awesome:",
        help=t("media.button_help"),
    ):
        _press(user_id, kind, found.getvalue(), day)
        st.session_state[ROUND_KEY] = st.session_state.get(ROUND_KEY, 0) + 1
        st.session_state[RESET_KEY] = True
        st.rerun()
