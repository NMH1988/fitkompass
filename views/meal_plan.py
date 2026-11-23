"""The coach's meal plan for a client (T11.7): the coach's form on Client week, the gymer's page.

The coach builds a plan on Client week while the client shares nutrition: one template day for
every day, of rows (a food from the USDA table, a meal slot from the food log's fixed list and
grams) added and removed in a draft before saving. The draft's totals per meal slot and for the day
show next to the client's target active today, and a plan whose day total is below the calorie
floor is refused, in the draft and by the store. Each save is a new plan that replaces the last;
"Remove the plan" saves an empty one. The gymer reads the active plan (the newest one their current
coach saved) on their own Meal plan page, read-only: nothing is logged from it. Every read and
write goes through the store with the session's own user ID (`views/account.py`), and nothing here
reaches a model.
"""

from dataclasses import asdict
from typing import NoReturn

import streamlit as st

from src import account as accounts
from src import chat, config, dashboard, diary, meal_plans
from src.store import meal_plans as store_plans
from src.store import users
from src.store.access import NotFound
from src.store.values import StoreValueError
from src.tools.food import food_names
from views import account, header, suggestions, tables
from views.text import label_of, plain, t

URL_PATH = "meal-plan"
# The coach's draft: {"for": the client's ID, "rows": [...], "saved": whether a plan with foods is
# saved}. Each row holds the meal slot, the USDA food and grams, and the nutrients of its grams for
# the draft's totals; Save looks every food up again, so the stored nutrients never come from the
# session. Kept in a plain session key (no widget key holds an ID); another client starts a new one.
DRAFT_KEY = "meal_plan_draft"
# The outcome of the coach's last change, shown once on the next run: ("saved" | "error", key).
FLASH_KEY = "meal_plan_flash"
ADD_FORM_KEY = "meal_plan_add"
_ROW_KEYS = ("meal", "fdc_id", "food_name", "grams", *meal_plans.NUTRIENTS)


def _totals_line(key: str, totals: dict[str, float], **params: object) -> str:
    """Return a totals line (a meal slot's or the day's) with each nutrient rounded."""
    return t(
        key,
        kcal=suggestions.nutrient(totals["kcal"]),
        protein=suggestions.nutrient(totals["protein_g"]),
        carbs=suggestions.nutrient(totals["carbohydrate_g"]),
        fat=suggestions.nutrient(totals["fat_g"]),
        **params,
    )


def _show_plan(items: list[dict]) -> None:
    """Show a plan's foods by meal slot, each slot's total, and the day's total."""
    meal_label = label_of("my_data.meal")
    by_meal = meal_plans.meal_totals(items)
    for meal, totals in by_meal.items():
        st.markdown(f"**{meal_label(meal)}**")
        lines = [f"- {suggestions.item_label(item)}" for item in items if item["meal"] == meal]
        st.markdown("\n".join(lines))
        st.caption(_totals_line("meal_plan.meal_total", totals, meal=meal_label(meal)))
    if items:
        st.markdown(f"**{_totals_line('meal_plan.total', meal_plans.totals(items))}**")


# --- The coach's form on Client week -------------------------------------------------------------


def _draft(user: dict, client_id: str) -> dict:
    """Return the coach's draft for this client, started from their saved plan."""
    kept = st.session_state.get(DRAFT_KEY)
    if kept is not None and kept["for"] == client_id:
        return kept
    rows: list[dict] = []
    try:
        with accounts.open_store(account.store_path()) as conn:
            saved = store_plans.current_meal_plan(conn, user["id"], client_id)
    except accounts.StoreUnavailable, NotFound:
        saved = None  # the Save then meets the same refusal, with its fixed message
    if saved is not None:
        rows = [{key: item[key] for key in _ROW_KEYS} for item in saved["items"]]
    draft = {"for": client_id, "rows": rows, "saved": bool(rows)}
    st.session_state[DRAFT_KEY] = draft
    return draft


def _flash(outcome: str, key: str) -> NoReturn:
    """Keep the outcome of the coach's change for the next run, and rerun (never returns)."""
    st.session_state[FLASH_KEY] = (outcome, key)
    st.rerun()


def _show_flash() -> None:
    """Show the outcome of the coach's last change once."""
    flash = st.session_state.pop(FLASH_KEY, None)
    if flash is None:
        return
    outcome, key = flash
    if outcome == "saved":
        st.success(t(key), icon=":material/check:")
    else:
        st.error(t(key), icon=":material/error:")


def _add(rows: list[dict], meal: object, name: object, grams: object) -> NoReturn:
    """Add a row to the draft after checking it; keep why it was refused otherwise."""
    if len(rows) >= config.MAX_MEAL_PLAN_FOODS:
        _flash("error", "meal_plan.full")
    try:
        item = meal_plans.planned_food(meal, name, grams)
    except diary.DiaryError as error:
        _flash("error", error.code)  # reruns: item is never read unset
    row = asdict(item)
    if any((r["meal"], r["fdc_id"]) == (row["meal"], row["fdc_id"]) for r in rows):
        _flash("error", "meal_plan.twice")
    rows.append(row)
    st.rerun()


def _write(user: dict, client_id: str, rows: list[dict] | None) -> NoReturn:
    """Save the draft as the client's new plan, or remove the plan when rows is None."""
    try:
        with accounts.open_store(account.store_path()) as conn:
            if rows is None:
                meal_plans.remove_meal_plan(conn, user["id"], client_id)
            else:
                meal_plans.save_meal_plan(
                    conn,
                    user["id"],
                    client_id,
                    [(row["meal"], row["food_name"], row["grams"]) for row in rows],
                )
    except accounts.StoreUnavailable:
        _flash("error", "account.store_unavailable")
    except NotFound:
        # Not a client who shares nutrition with this coach (any more): one message for every case.
        _flash("error", "meal_plan.refused")
    except diary.DiaryError as error:
        _flash("error", error.code)
    except StoreValueError:
        _flash("error", "meal_plan.invalid")
    st.session_state.pop(DRAFT_KEY, None)  # read again from the saved plan
    _flash("saved", "meal_plan.removed" if rows is None else "meal_plan.saved")


def _targets_line(user: dict, client_id: str) -> None:
    """Show the client's target active today next to the draft's totals."""
    target = suggestions.target_today(user, client_id)
    if target is None:
        st.caption(t("suggestions.no_target"))
        return
    st.caption(
        t(
            "suggestions.target",
            kcal=suggestions.nutrient(target.kcal),
            protein=suggestions.nutrient(target.protein_g),
            carbs=suggestions.nutrient(target.carbohydrate_g),
            fat=suggestions.nutrient(target.fat_g),
        )
    )


def _add_form(rows: list[dict]) -> None:
    """Show the form that adds one food, its grams and its meal slot to the draft."""
    try:
        names = food_names()
    except Exception:
        # A missing or broken table: the fixed message, never the exception's text.
        st.error(t("diary.food_table"), icon=":material/error:")
        names = ()
    with st.form(ADD_FORM_KEY, clear_on_submit=True, border=True):
        food = st.selectbox(
            t("today.food"),
            names,
            index=None,
            placeholder=t("today.food_placeholder"),
            key="meal_plan_food",
        )
        grams_column, meal_column = st.columns([1, 2], vertical_alignment="bottom")
        grams = grams_column.number_input(
            t("today.grams"),
            min_value=config.FOOD_MIN_GRAMS,
            max_value=float(config.FOOD_MAX_GRAMS),
            value=config.DIARY_DEFAULT_GRAMS,
            step=config.DIARY_STEP_GRAMS,
            format="%.1f",
            key="meal_plan_grams",
        )
        meal = meal_column.segmented_control(
            t("today.meal"),
            tables.MEALS,
            format_func=label_of("my_data.meal"),
            key="meal_plan_meal",
            width="stretch",
        )
        added = st.form_submit_button(
            t("meal_plan.add_row"), icon=":material/add:", disabled=not names
        )
    if added:
        _add(rows, meal, food, grams)


def _remove_row(rows: list[dict]) -> None:
    """Show the picker and button that take one row out of the draft."""
    meal_label = label_of("my_data.meal")
    remove_column, button_column = st.columns([3, 2], vertical_alignment="bottom")
    # Plain text (a selectbox renders no Markdown), so the name is not escaped here.
    labels = [
        f"{meal_label(row['meal'])}: {row['food_name']}, {plain(row['grams'])} g" for row in rows
    ]
    picked = remove_column.selectbox(
        t("meal_plan.remove_pick"),
        range(len(rows)),
        format_func=labels.__getitem__,
        index=None,
        key="meal_plan_remove_pick",
    )
    if button_column.button(
        t("meal_plan.remove_row"), icon=":material/remove:", key="meal_plan_remove_row"
    ) and (picked is not None):
        rows.pop(picked)
        st.session_state.pop("meal_plan_remove_pick", None)
        st.rerun()


def coach_section(user: dict, client_id: str, week: dashboard.DashboardWeek) -> None:
    """Show the coach's meal plan for the client, or why it is not offered."""
    st.subheader(f":material/menu_book: {t('meal_plan.coach_heading')}")
    _show_flash()
    if "nutrition" not in week.shared:
        st.caption(t("meal_plan.not_shared"))
        return
    st.caption(t("meal_plan.coach_intro"))
    draft = _draft(user, client_id)
    rows = draft["rows"]
    if not rows:
        st.caption(t("meal_plan.draft_empty"))
    _show_plan(rows)
    if rows:
        _targets_line(user, client_id)
        if meal_plans.below_floor(rows):
            st.warning(t("meal_plan.below_floor_draft"), icon=":material/warning:")
        st.caption(t("usda.source_line"))
    _add_form(rows)
    if rows:
        _remove_row(rows)
    save_column, remove_column = st.columns(2)
    if save_column.button(
        t("meal_plan.save"),
        type="primary",
        icon=":material/save:",
        key="meal_plan_save",
        disabled=not rows,
    ):
        _write(user, client_id, rows)
    if draft["saved"] and remove_column.button(
        t("meal_plan.remove_plan"), icon=":material/delete:", key="meal_plan_remove_plan"
    ):
        _write(user, client_id, None)


# --- The gymer's Meal plan page ------------------------------------------------------------------


def _read_own(user_id: str) -> tuple[dict | None, str | None, bool]:
    """Return the gymer's active plan, its coach's name and whether they have a coach now."""
    with accounts.open_store(account.store_path()) as conn:
        plan = store_plans.current_meal_plan(conn, user_id, user_id)
        has_coach = any(
            row["status"] == "active" for row in users.list_relationships(conn, user_id)
        )
        name = None if plan is None else users.display_name_of(conn, user_id, plan["coach_id"])
    return plan, name, has_coach


def page() -> None:
    """Show the gymer's Meal plan page: their current coach's plan, read-only."""
    with header.main_column():
        header.show()
        account.store_notice()
        user = account.current_user()
        if user is None or user["role"] != "gymer":
            return  # not registered for them (views/navigation.py); never reached
        st.subheader(t("page.meal_plan"))
        try:
            plan, coach_name, has_coach = _read_own(user["id"])
        except accounts.StoreUnavailable:
            st.error(t("account.store_unavailable"), icon=":material/error:")
            return
        except NotFound:
            return  # the account was deleted in another tab: the next run shows the welcome page
        if not has_coach:
            st.caption(t("meal_plan.no_coach"))
            return
        if plan is None or not plan["items"]:
            st.caption(t("meal_plan.none"))
            return
        # A display name is checked when it is chosen; escaped all the same (the other side's).
        st.markdown(t("meal_plan.gymer_intro", coach=chat.escape_markdown(coach_name)))
        st.caption(t("meal_plan.saved_at", when=tables.berlin_time(plan["created_at"])))
        st.info(t("meal_plan.not_checked"), icon=":material/info:")
        with st.container(border=True):
            _show_plan(plan["items"])
        st.caption(f"{t('meal_plan.usda_note')} {t('usda.source_line')}")
