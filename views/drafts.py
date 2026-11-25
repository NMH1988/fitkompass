"""A gymer's AI drafts of log entries from their own messages, on the Messages page (T11.5).

Consent (a) is given or withdrawn here in one click, with its text (`src/drafting.py`); a consent
to an older text counts as none and asks again. Only with it, and only when the gymer presses the
button, does `src/agent/drafts.py` read the gymer's own undrafted messages of the diary's window
and pause on a message's
cards: each card says it was drafted by an AI model, and the gymer approves, edits or rejects every
card of the message, then saves them in one step. Withdrawing the consent drops the pending drafts
at once. The run lives in this session only (`Drafter`), keyed by the acting user.
"""

from datetime import date

import streamlit as st

from src import account as accounts
from src import chat, config, diary, drafting, exercises, guard, i18n, metrics, units
from src.agent import drafts as workflow
from src.agent import graph
from src.store import ai_consents, messages
from src.store.access import NotFound
from src.tools.food import food_names
from views import account, resources, tables
from views.text import label_of, lang, t

FLASH_KEY = "drafts_flash"
# What the gymer picks on a card; an approved card whose values were changed is sent as an edit.
_CHOICES = ("approve", "reject")


def _drafter(user_id: str) -> workflow.Drafter:
    """Return the session's drafting runs of this user (demo mode can switch users)."""
    key = f"drafts_drafter_{user_id}"
    if key not in st.session_state:
        st.session_state[key] = workflow.Drafter()
    return st.session_state[key]


def _context(prompt: chat.Prompt | None = None) -> workflow.DraftContext:
    """Return a run's context: the store file, the cached model and the owner's instruction."""
    # A new run reads the instruction file; a decision passes the one its run started with.
    found = prompt or graph.load_prompt(
        config.DRAFT_PROMPT_PATH, config.DRAFT_PROMPT_MISSING_MESSAGE, "prompt.drafts_missing"
    )
    return workflow.DraftContext(
        store_path=account.store_path(), prompt=found, chat_model=resources.draft_model
    )


def _consent(user_id: str) -> bool:
    """Show consent (a) with its one-click button; return whether it holds for this text."""
    version = drafting.consent_version()
    try:
        with accounts.open_store(account.store_path()) as conn:
            current = ai_consents.current(conn, user_id, drafting.PURPOSE)
    except accounts.StoreUnavailable:
        st.error(t("account.store_unavailable"), icon=":material/error:")
        return False
    except NotFound:
        return False
    given = current is not None and current["text_version"] == version
    st.caption(drafting.consent_text(lang()))
    if given:
        st.caption(f":material/check_circle: {t('drafts.consent_given')}")
        if st.button(t("drafts.consent_withdraw"), key="drafts_withdraw"):
            _set_consent(user_id, give=False)
        return True
    if current is not None:
        st.warning(t("drafts.consent_changed"), icon=":material/update:")
    give, withdraw = st.columns(2)
    if give.button(t("drafts.consent_give"), key="drafts_give", type="primary"):
        _set_consent(user_id, give=True)
    # A consent to an older text still open is withdrawn here too, not only renewed.
    if current is not None and withdraw.button(t("drafts.consent_withdraw"), key="drafts_withdraw"):
        _set_consent(user_id, give=False)
    return False


def _set_consent(user_id: str, *, give: bool) -> None:
    """Give or withdraw consent (a); a withdrawal drops the pending drafts at once."""
    try:
        with accounts.open_store(account.store_path()) as conn:
            if give:
                ai_consents.give(conn, user_id, drafting.PURPOSE, drafting.consent_version())
            else:
                ai_consents.withdraw(conn, user_id, drafting.PURPOSE)
    except accounts.StoreUnavailable, NotFound:
        st.error(t("account.store_unavailable"), icon=":material/error:")
        return
    if not give:
        _drafter(user_id).drop()
        st.session_state[FLASH_KEY] = ("info", "drafts.consent_withdrawn", {})
    st.rerun()


def _flash(result: workflow.RunResult) -> None:
    """Keep a run's outcome to show on the next run of the page."""
    counts = result.counts
    if result.outcome == "error":
        # The error's own fixed text (a bad key, no credit, a timeout, the store), then the note
        # that nothing more was logged.
        code = result.error_code if result.error_code in i18n.TEXT["en"] else "llm.error"
        found = [("error", code, {}), ("info", "drafts.error", {})]
    elif result.outcome == "nothing":
        found = ("info", "drafts.nothing", {})
    elif result.outcome == "no_consent":
        found = ("warning", "drafts.no_consent", {})
    elif result.outcome == "profile_first":
        found = ("warning", "diary.profile_first", {})
    elif result.outcome == "not_found":
        found = ("warning", "drafts.only_active", {})
    elif result.outcome == "done":
        params = {name: counts.get(name, 0) for name in ("cards", "refused", "dropped")}
        found = ("success", "drafts.done", params)
    else:
        found = None
    notes = []
    if result.last == "already":
        notes.append(("warning", "drafts.already", {}))
    elif result.last == "saved":
        notes.append(("success", "drafts.saved", {"count": result.step_logged}))
    if isinstance(found, tuple):
        found = [found]
    st.session_state[FLASH_KEY] = [*notes, *(found or [])]


def _show_flash() -> None:
    """Show the last action's outcome once, in the chosen language."""
    found = st.session_state.pop(FLASH_KEY, None)
    if not found:
        return
    for kind, key, params in [found] if isinstance(found, tuple) else found:
        getattr(st, kind)(t(key, **params))


def _press(user_id: str, thread_id: int) -> None:
    """Run the workflow up to the first message's cards (or its end) on the gymer's press."""
    try:
        context = _context()
    except chat.PromptMissingError as exc:
        st.session_state[FLASH_KEY] = ("error", exc.code, {})
        return
    # A press spends up to DRAFT_MAX_MESSAGES_PER_RUN model calls, so it counts against the
    # session's limit, as a chat question and a weekly review do; a refusal makes no call.
    refused = guard.session_limiter(st.session_state).try_acquire()
    if refused is not None:
        st.session_state[FLASH_KEY] = ("warning", f"drafts.{refused.reason.value}", refused.params)
        return
    with st.spinner(t("drafts.button")):
        result = _drafter(user_id).start(context, user_id, thread_id)
    _flash(result)


def _message_text(user_id: str, thread_id: int, message_id: int) -> str | None:
    """Return the gymer's own message the cards were drafted from, to show above them."""
    try:
        with accounts.open_store(account.store_path()) as conn:
            rows = messages.list_messages(conn, user_id, thread_id)
    except accounts.StoreUnavailable, NotFound:
        return None
    return next((row["text"] for row in rows if row["id"] == message_id), None)


def _day_input(card: dict, key: str) -> date:
    """Show a card's day, within the diary's window."""
    today = metrics.berlin_day()
    low = date.fromordinal(today.toordinal() - config.DIARY_MAX_DAYS_BACK)
    value = min(max(date.fromisoformat(card["day"]), low), today)
    return st.date_input(t("drafts.day"), value=value, min_value=low, max_value=today, key=key)


def _summary(card: dict) -> str:
    """Return a card's grams and day as one labelled line, saying when the grams are missing."""
    parts = []
    if card["kind"] == "food":
        grams = card["grams"]
        if grams is None:
            parts.append(t("drafts.grams_missing"))
        else:
            parts.append(t("drafts.grams_line", grams=i18n.plain(grams, lang())))
    parts.append(t("drafts.day_line", day=card["day"]))
    return " · ".join(parts)


def _logged_on(user_id: str, days: set[str]) -> list[dict]:
    """Return the gymer's own food entries of the cards' days (empty if the store failed)."""
    found: list[dict] = []
    try:
        with accounts.open_store(account.store_path()) as conn:
            for day in sorted(days):
                found.extend(diary.day_items(conn, user_id, date.fromisoformat(day)))
    except accounts.StoreUnavailable, NotFound, ValueError:
        return []
    return found


def _food_card(card: dict, key: str, names: tuple[str, ...], logged: list[dict]) -> dict:
    """Show a food card and its edit fields; return the edited card."""
    name = card["food_name"]
    st.markdown(f"**{t('drafts.card_food')}:** {chat.escape_markdown(name or '-')}")
    if card.get("asked"):
        # The model's own words for the food, so a wrong match shows.
        st.caption(t("drafts.read_as", food=chat.escape_markdown(card["asked"])))
    nutrients = drafting.food_nutrients(card)
    if nutrients is not None:
        st.caption(
            t(
                "drafts.nutrients",
                kcal=round(nutrients["kcal"]),
                protein=round(nutrients["protein_g"], 1),
                carbs=round(nutrients["carbohydrate_g"], 1),
                fat=round(nutrients["fat_g"], 1),
            )
        )
    for item in drafting.already_logged(card, logged):
        st.warning(
            t(
                "drafts.already_logged",
                food=chat.escape_markdown(item["food_name"]),
                grams=i18n.plain(round(item["grams"], 1), lang()),
                meal=label_of("my_data.meal")(item["meal"]),
                day=card["day"],
            ),
            icon=":material/content_copy:",
        )
    # What Approve saves unless changed below: the grams and the day (the meal slot is picked
    # under it).
    st.caption(_summary(card))
    for missing, note in (
        (name is None, "drafts.no_match"),
        (card["grams"] is None, "drafts.no_grams"),
    ):
        if missing:
            st.caption(f":material/edit_note: {t(note)}")
    # The meal slot is picked on the card itself: a message often names none.
    meal = st.selectbox(
        t("drafts.meal"),
        tables.MEALS,
        index=tables.MEALS.index(card["meal"]) if card["meal"] in tables.MEALS else None,
        format_func=label_of("my_data.meal"),
        placeholder=t("drafts.meal_placeholder"),
        key=f"{key}_meal",
    )
    with st.expander(t("drafts.change")):
        options = list(dict.fromkeys([*card["alternatives"], *names]))
        food = st.selectbox(
            t("drafts.food"),
            options,
            index=options.index(name) if name in options else None,
            key=f"{key}_food",
        )
        grams = st.number_input(
            t("drafts.grams"),
            min_value=config.FOOD_MIN_GRAMS,
            max_value=float(config.FOOD_MAX_GRAMS),
            value=card["grams"],  # empty when the message names no amount
            step=config.DIARY_STEP_GRAMS,
            key=f"{key}_grams",
        )
        day = _day_input(card, f"{key}_day")
    return {**card, "food_name": food, "grams": grams, "meal": meal, "day": day.isoformat()}


def _weight_card(card: dict, key: str) -> dict:
    """Show a weight card and its edit fields; return the edited card."""
    st.markdown(f"**{t('drafts.card_weight')}:** {card['weight_kg']} kg")
    st.caption(_summary(card))
    low, high = config.PROFILE_WEIGHT_KG_RANGE
    with st.expander(t("drafts.change")):
        weight = st.number_input(
            t("drafts.weight_kg"),
            min_value=float(low),
            max_value=float(high),
            value=float(card["weight_kg"]),
            step=10**-units.WEIGHT_DECIMALS,
            key=f"{key}_kg",
        )
        day = _day_input(card, f"{key}_day")
    return {**card, "weight_kg": weight, "day": day.isoformat()}


def _workout_card(card: dict, key: str) -> dict:
    """Show a workout card and its edit fields; return the edited card."""
    current = lang()
    st.markdown(f"**{t('drafts.card_workout')}**")
    st.caption(_summary(card))
    for number, one in enumerate(card["sets"], start=1):
        label = tables.exercise_label(one["exercise_id"], current)
        st.caption(
            f"{t('drafts.set', number=number)}: {label} · {one['reps']} × {one['weight_kg']} kg"
        )
    edited = []
    low, high = config.WORKOUT_REPS_RANGE
    kg_low, kg_high = config.WORKOUT_WEIGHT_KG_RANGE
    ids = list(exercises.exercise_ids())
    with st.expander(t("drafts.change")):
        for number, one in enumerate(card["sets"], start=1):
            name, reps, load = st.columns([3, 1, 1])
            exercise = name.selectbox(
                t("drafts.set", number=number),
                ids,
                index=ids.index(one["exercise_id"]),
                format_func=lambda exercise_id: tables.exercise_label(exercise_id, current),
                key=f"{key}_{number}_exercise",
            )
            count = reps.number_input(
                t("drafts.reps"),
                min_value=low,
                max_value=high,
                value=one["reps"],
                key=f"{key}_{number}_reps",
            )
            weight = load.number_input(
                t("drafts.load_kg"),
                min_value=float(kg_low),
                max_value=float(kg_high),
                value=float(one["weight_kg"]),
                step=config.WORKOUT_WEIGHT_STEP["metric"],
                key=f"{key}_{number}_kg",
            )
            edited.append({"exercise_id": exercise, "reps": count, "weight_kg": weight})
        day = _day_input(card, f"{key}_day")
    return {**card, "sets": edited, "day": day.isoformat()}


def _progress(pending: workflow.RunResult) -> str:
    """Return where the run stands: this message's number, and how many were passed over."""
    line = t("drafts.progress", position=pending.position, total=pending.total)
    if pending.skipped:
        line += " · " + t("drafts.skipped", count=pending.skipped)
    return line


def _cards(user_id: str, thread_id: int, pending: workflow.RunResult) -> None:
    """Show one message's cards with a decision each, saved together in one step."""
    st.info(t("drafts.ai_label", provider=drafting.model_provider()), icon=":material/smart_toy:")
    text = _message_text(user_id, thread_id, pending.message_id)
    st.caption(_progress(pending))
    st.markdown(f"**{t('drafts.your_message', day=pending.message_day)}**")
    if text is not None:
        st.text(text)
    if pending.error is not None:
        st.error(t(pending.error), icon=":material/error:")
    names = food_names()
    # The gymer's own entries of the cards' days, read once, for the "already logged" notes.
    logged = _logged_on(user_id, {card["day"] for card in pending.cards if card["kind"] == "food"})
    form_key = f"drafts_form_{pending.message_id}"
    with st.form(form_key):
        choices = []
        for index, card in enumerate(pending.cards):
            key = f"{form_key}_{index}"
            with st.container(border=True):
                if card["kind"] == "food":
                    edited = _food_card(card, key, names, logged)
                elif card["kind"] == "weight":
                    edited = _weight_card(card, key)
                else:
                    edited = _workout_card(card, key)
                # No choice is made for the gymer: every card needs its own Approve or Reject.
                action = st.segmented_control(
                    t("drafts.action"),
                    _CHOICES,
                    format_func=label_of("drafts.action"),
                    key=f"{key}_action",
                )
            choices.append((action, card, edited))
        saved = st.form_submit_button(t("drafts.save"), type="primary", icon=":material/save:")
    if saved:
        # Approve saves what the card shows: changed values go as an edit, which the workflow
        # checks again like every decision.
        decisions = [
            {"action": "edit", "card": edited}
            if action == "approve" and edited != card
            else {"action": action}
            for action, card, edited in choices
        ]
        drafter = _drafter(user_id)
        try:
            # The run resumes with the instruction it started with, so cards already drafted can
            # be saved even if the file is missing now.
            context = _context(drafter.prompt)
        except chat.PromptMissingError as exc:
            st.session_state[FLASH_KEY] = ("error", exc.code, {})
            st.rerun()
        _flash(drafter.decide(context, decisions))
        st.rerun()


def standing_consent(user_id: str) -> None:
    """Show consent (a) with its withdraw button where no draft runs, if it is still given."""
    # The consent is the gymer's, not a thread's: it stays given after a relationship ends, so it
    # can be withdrawn in one click with no active thread too (GDPR Art. 7(3)).
    try:
        with accounts.open_store(account.store_path()) as conn:
            current = ai_consents.current(conn, user_id, drafting.PURPOSE)
    except accounts.StoreUnavailable, NotFound:
        return
    if current is None:
        _show_flash()
        return
    st.divider()
    st.markdown(f"**{t('drafts.title')}**")
    _show_flash()
    st.caption(t("drafts.consent_standing"))
    if st.button(t("drafts.consent_withdraw"), key="drafts_withdraw_standing"):
        _drafter(user_id).drop()
        _set_consent(user_id, give=False)


def section(user_id: str, thread: dict) -> None:
    """Show consent (a), the button and the cards on an active thread; drop an ended one's run."""
    if thread["status"] != "active":
        if _drafter(user_id).relationship_id == thread["id"]:
            _drafter(user_id).drop()  # the run's relationship ended: its drafts go at once
        standing_consent(user_id)
        return
    st.divider()
    st.markdown(f"**{t('drafts.title')}**")
    _show_flash()
    if not _consent(user_id):
        _drafter(user_id).drop()  # e.g. withdrawn in another tab: no draft is kept
        return
    drafter = _drafter(user_id)
    if drafter.relationship_id not in (None, thread["id"]):
        drafter.drop()  # a run of an earlier relationship: none of its messages goes further
    pending = drafter.pending()
    if pending is not None:
        _cards(user_id, thread["id"], pending)
        return
    help_text = t(
        "drafts.button_help",
        count=config.DRAFT_MAX_MESSAGES_PER_RUN,
        days=config.DIARY_MAX_DAYS_BACK,
    )
    if st.button(
        t("drafts.button"), key="drafts_start", icon=":material/auto_awesome:", help=help_text
    ):
        _press(user_id, thread["id"])
        st.rerun()
