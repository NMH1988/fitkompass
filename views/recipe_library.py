"""The coach's Recipe library (T11.8): their own recipes, written, edited, deleted and rated.

A coach writes a recipe in a draft: a name, the steps in their own words (Markdown, shown with
images and links as plain text) and rows of a USDA food with grams, added and taken out before
saving; Save looks every food up again in the USDA table, so the stored nutrients never come from
the session. An edit saves a new version that keeps the recipe's ratings; Delete asks first, and
removes the recipe with its ratings while the meals clients logged from it stay. Each recipe shows
its average and count only once enough clients who share nutrition have rated it
(`config.RATING_MIN_RATERS`), never who rated. Every read and write goes through the store with the
session's own user ID (`views/account.py`), and nothing here reaches a model.
"""

from typing import NoReturn

import streamlit as st

from src import account as accounts
from src import config, diary
from src import recipes as recipe_service
from src.store import ratings
from src.store import recipes as store_recipes
from src.store.access import NotFound
from src.store.values import StoreValueError
from src.tools.food import food_names
from views import account, header, recipes
from views.text import n, plain, t

URL_PATH = "recipe-library"
# The coach's draft: {"id": the recipe's ID or None for a new one, "rows": [...]}, each row a USDA
# food, its grams and the nutrients of its grams for the draft's totals. The name and steps live in
# their widgets' keys. Kept in a plain session key (no widget key holds an ID).
DRAFT_KEY = "recipe_draft"
NAME_KEY = "recipe_name"
STEPS_KEY = "recipe_steps"
# The recipe whose Edit the coach pressed, opened in the draft on the next run before its fields are
# drawn (a widget's value cannot be set once it is drawn in a run).
EDIT_KEY = "recipe_edit"
# The recipe whose Delete the coach pressed, waiting for the confirmation.
DELETE_KEY = "recipe_delete"
# The outcome of the coach's last change, shown once on the next run: ("saved" | "error", key).
FLASH_KEY = "recipe_library_flash"
ADD_FORM_KEY = "recipe_add"
REMOVE_PICK_KEY = "recipe_remove_pick"
_ROW_KEYS = ("fdc_id", "food_name", "grams", *recipe_service.NUTRIENTS)


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


def _draft() -> dict:
    """Return the coach's draft, a new recipe's when none is open."""
    draft = st.session_state.get(DRAFT_KEY)
    if draft is None:
        draft = {"id": None, "rows": []}
        st.session_state[DRAFT_KEY] = draft
    return draft


def _open_edit(recipe: dict) -> None:
    """Open the draft from a saved recipe's newest version, before its fields are drawn."""
    st.session_state[DRAFT_KEY] = {
        "id": recipe["id"],
        "rows": [{key: food[key] for key in _ROW_KEYS} for food in recipe["ingredients"]],
    }
    st.session_state[NAME_KEY] = recipe["name"]
    st.session_state[STEPS_KEY] = recipe["steps"]
    # A pick of the last draft's foods could point past the end of this one's list.
    st.session_state.pop(REMOVE_PICK_KEY, None)


def _clear_draft() -> None:
    """Close the draft and empty its fields."""
    for key in (DRAFT_KEY, NAME_KEY, STEPS_KEY, REMOVE_PICK_KEY):
        st.session_state.pop(key, None)


def _add(rows: list[dict], name: object, grams: object) -> NoReturn:
    """Add a food to the draft after checking it; keep why it was refused otherwise."""
    if len(rows) >= config.MAX_RECIPE_INGREDIENTS:
        _flash("error", "recipes.full")
    try:
        item = recipe_service.ingredient(name, grams)
    except diary.DiaryError as error:
        _flash("error", error.code)  # reruns: item is never read unset
    if any(row["fdc_id"] == item.fdc_id for row in rows):
        _flash("error", "recipes.twice")
    rows.append({key: getattr(item, key) for key in _ROW_KEYS})
    st.rerun()


def _save(user: dict, draft: dict, name: object, steps: object) -> NoReturn:
    """Save the draft as a new recipe or a new version of the one being edited."""
    try:
        with accounts.open_store(account.store_path()) as conn:
            recipe_service.save_recipe(
                conn,
                user["id"],
                draft["id"],
                name=name,
                steps=steps,
                rows=[(row["food_name"], row["grams"]) for row in draft["rows"]],
            )
    except accounts.StoreUnavailable:
        _flash("error", "account.store_unavailable")
    except NotFound:
        # Deleted in another tab, or not this coach's: one message for every case.
        _flash("error", "recipes.refused")
    except diary.DiaryError as error:
        _flash("error", error.code)
    except StoreValueError:
        _flash("error", "recipes.invalid")
    _clear_draft()
    _flash("saved", "recipes.saved")


def _delete(user: dict, recipe_id: int) -> NoReturn:
    """Delete one of the coach's recipes after the confirmation."""
    st.session_state.pop(DELETE_KEY, None)
    try:
        with accounts.open_store(account.store_path()) as conn:
            store_recipes.delete_recipe(conn, user["id"], recipe_id)
    except accounts.StoreUnavailable:
        _flash("error", "account.store_unavailable")
    except NotFound:
        _flash("error", "recipes.refused")
    if (st.session_state.get(DRAFT_KEY) or {}).get("id") == recipe_id:
        _clear_draft()
    _flash("saved", "recipes.deleted")


def _add_form(rows: list[dict]) -> None:
    """Show the form that adds one food and its grams to the draft."""
    try:
        names = food_names()
    except Exception:
        # A missing or broken table: the fixed message, never the exception's text.
        st.error(t("diary.food_table"), icon=":material/error:")
        names = ()
    with st.form(ADD_FORM_KEY, clear_on_submit=True, border=True):
        food_column, grams_column = st.columns([3, 1], vertical_alignment="bottom")
        food = food_column.selectbox(
            t("today.food"),
            names,
            index=None,
            placeholder=t("today.food_placeholder"),
            key="recipe_food",
        )
        grams = grams_column.number_input(
            t("today.grams"),
            min_value=config.FOOD_MIN_GRAMS,
            max_value=float(config.FOOD_MAX_GRAMS),
            value=config.DIARY_DEFAULT_GRAMS,
            step=config.DIARY_STEP_GRAMS,
            format="%.1f",
            key="recipe_grams",
        )
        added = st.form_submit_button(
            t("recipes.add_food"), icon=":material/add:", disabled=not names
        )
    if added:
        _add(rows, food, grams)


def _remove_row(rows: list[dict]) -> None:
    """Show the picker and button that take one food out of the draft."""
    remove_column, button_column = st.columns([3, 2], vertical_alignment="bottom")
    # Plain text (a selectbox renders no Markdown), so the name is not escaped here.
    labels = [f"{row['food_name']}, {plain(row['grams'])} g" for row in rows]
    picked = remove_column.selectbox(
        t("recipes.remove_pick"),
        range(len(rows)),
        format_func=labels.__getitem__,
        index=None,
        key=REMOVE_PICK_KEY,
    )
    if button_column.button(
        t("recipes.remove_food"), icon=":material/remove:", key="recipe_remove_food"
    ) and (picked is not None):
        rows.pop(picked)
        st.session_state.pop(REMOVE_PICK_KEY, None)
        st.rerun()


def _editor(user: dict, recipes_by_id: dict[int, dict]) -> None:
    """Show the draft: its name, steps and foods, and the buttons that save or cancel it."""
    pending = st.session_state.pop(EDIT_KEY, None)
    if pending in recipes_by_id:
        _open_edit(recipes_by_id[pending])
    draft = _draft()
    editing = recipes_by_id.get(draft["id"]) if draft["id"] is not None else None
    if draft["id"] is not None and editing is None:
        _clear_draft()  # deleted in another tab: start a new recipe instead
        draft = _draft()
    heading = (
        t("recipes.new") if editing is None else t("recipes.editing", name=recipes.title(editing))
    )
    with st.expander(heading, icon=":material/edit_note:", expanded=editing is not None):
        name = st.text_input(
            t("recipes.name"), max_chars=config.RECIPE_NAME_MAX_CHARS, key=NAME_KEY
        )
        steps = st.text_area(
            t("recipes.steps"),
            max_chars=config.RECIPE_STEPS_MAX_CHARS,
            help=t("recipes.steps_help"),
            key=STEPS_KEY,
        )
        st.markdown(f"**{t('recipes.foods')}**")
        rows = draft["rows"]
        if rows:
            recipes.show_foods(rows)
        else:
            st.caption(t("recipes.draft_empty"))
        _add_form(rows)
        if rows:
            _remove_row(rows)
        save_column, cancel_column = st.columns(2)
        if save_column.button(
            t("recipes.save"),
            type="primary",
            icon=":material/save:",
            key="recipe_save",
            disabled=not rows,
        ):
            _save(user, draft, name, steps)
        if (editing is not None or rows) and cancel_column.button(
            t("recipes.cancel"), icon=":material/close:", key="recipe_cancel"
        ):
            _clear_draft()
            st.rerun()


def _rating_line(summary: tuple[float, int] | None) -> str:
    """Return a recipe's rating as the coach sees it: the average and count, or not enough yet."""
    if summary is None:
        return t("recipes.rating_not_enough")
    average, count = summary
    return t("recipes.rating_line", average=plain(round(average, 1)), count=n(count))


def _recipe(user: dict, recipe: dict, summary: tuple[float, int] | None) -> None:
    """Show one of the coach's recipes with its rating and its Edit and Delete buttons."""
    with st.expander(recipes.title(recipe), icon=":material/menu_book:"):
        st.caption(f":material/star: {_rating_line(summary)}")
        recipes.show_foods(recipe["ingredients"])
        recipes.show_steps(recipe["steps"])
        if st.session_state.get(DELETE_KEY) == recipe["id"]:
            st.warning(t("recipes.delete_confirm"), icon=":material/warning:")
            yes_column, no_column = st.columns(2)
            if yes_column.button(
                t("recipes.delete_yes"), type="primary", key=f"recipe_delete_yes_{recipe['id']}"
            ):
                _delete(user, recipe["id"])
            if no_column.button(t("recipes.delete_no"), key=f"recipe_delete_no_{recipe['id']}"):
                st.session_state.pop(DELETE_KEY, None)
                st.rerun()
            return
        edit_column, delete_column = st.columns(2)
        if edit_column.button(
            t("recipes.edit"), icon=":material/edit:", key=f"recipe_edit_{recipe['id']}"
        ):
            st.session_state[EDIT_KEY] = recipe["id"]
            st.rerun()
        if delete_column.button(
            t("recipes.delete"), icon=":material/delete:", key=f"recipe_delete_{recipe['id']}"
        ):
            st.session_state[DELETE_KEY] = recipe["id"]
            st.rerun()


def page() -> None:
    """Show the coach's Recipe library: their recipes with ratings, and the draft."""
    with header.main_column():
        header.show()
        account.store_notice()
        user = account.current_user()
        if user is None or user["role"] != "coach":
            return  # not registered for them (views/navigation.py); never reached
        st.subheader(t("page.recipe_library"))
        _show_flash()
        st.caption(t("recipes.coach_intro"))
        st.info(t("recipes.coach_not_checked"), icon=":material/info:")
        try:
            with accounts.open_store(account.store_path()) as conn:
                found = store_recipes.list_recipes(conn, user["id"])
                summaries = ratings.rating_summaries(conn, user["id"])
        except accounts.StoreUnavailable:
            st.error(t("account.store_unavailable"), icon=":material/error:")
            return
        except NotFound:
            return  # the account was deleted in another tab: the next run shows the welcome page
        _editor(user, {recipe["id"]: recipe for recipe in found})
        if not found:
            st.caption(t("recipes.none_coach"))
        else:
            st.caption(t("recipes.rating_note_coach"))
        for recipe in found:
            _recipe(user, recipe, summaries.get(recipe["id"]))
        st.caption(f"{t('recipes.usda_note')} {t('usda.source_line')}")
