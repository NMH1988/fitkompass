"""The gymer's Recipes page (T11.8): their current coach's recipes, logged in a click and rated.

The gymer reads the recipes of the coach they are connected with now, once they have saved a
profile (whose first Save carries the 18+ check), as the Meal plan page does. Each recipe shows its
foods at the portion the gymer chooses, its totals and the coach's steps (Markdown with images and
links as plain text, `src/recipes.steps_markdown()`), and logs to the day and meal the gymer picks:
one diary entry per food, marked as from the recipe, which the store checks. A gymer who logged a
recipe rates it from 1 to 5 stars; the page says what the coach sees of it. Every read and write
goes through the store with the session's own user ID (`views/account.py`), and nothing here
reaches a model. The display helpers here are shared with the coach's Recipe library.
"""

import sqlite3
from collections.abc import Callable
from datetime import date, timedelta
from typing import NoReturn

import streamlit as st

from src import account as accounts
from src import chat, config, diary, i18n, metrics
from src import recipes as recipe_service
from src.store import ratings, users
from src.store import recipes as store_recipes
from src.store.access import NotFound
from views import account, header, suggestions, tables
from views.text import label_of, lang, t

URL_PATH = "recipes"
# The outcome of the gymer's last log or rating, shown once on the next run: ("saved" | "error",
# key).
FLASH_KEY = "recipes_flash"


def portions() -> list[float]:
    """Return the portion factors the page offers, from the range in config by its step."""
    low, high = config.RECIPE_PORTION_RANGE
    count = round((high - low) / config.RECIPE_PORTION_STEP)
    return [low + index * config.RECIPE_PORTION_STEP for index in range(count + 1)]


def portion_format() -> Callable[[float], str]:
    """Return the portion picker's format_func ("1.5×", "1,5×"), in today's language."""
    # The language is bound now: Streamlit (and AppTest) may call format_func outside the run.
    current = lang()
    return lambda factor: f"{i18n.plain(factor, current)}×"


def show_foods(foods: list[dict]) -> None:
    """Show a recipe's foods with their grams and energy, then the total."""
    lines = [
        "- "
        + t(
            "recipes.food_line",
            food=chat.escape_markdown(food["food_name"]),
            grams=suggestions.nutrient(food["grams"]),
            kcal=suggestions.nutrient(food["kcal"]),
        )
        for food in foods
    ]
    st.markdown("\n".join(lines))
    total = recipe_service.totals(foods)
    st.caption(
        t(
            "recipes.total",
            kcal=suggestions.nutrient(total["kcal"]),
            protein=suggestions.nutrient(total["protein_g"]),
            carbs=suggestions.nutrient(total["carbohydrate_g"]),
            fat=suggestions.nutrient(total["fat_g"]),
        )
    )


def show_steps(steps: str) -> None:
    """Show the coach's steps as Markdown that loads no image and links nowhere."""
    st.markdown(recipe_service.steps_markdown(steps))


def title(recipe: dict) -> str:
    """Return a recipe's name, escaped, for an expander's label."""
    return chat.escape_markdown(recipe["name"])


def _flash(outcome: str, key: str) -> NoReturn:
    """Keep the outcome of the gymer's action for the next run, and rerun (never returns)."""
    st.session_state[FLASH_KEY] = (outcome, key)
    st.rerun()


def _show_flash() -> None:
    """Show the outcome of the gymer's last action once."""
    flash = st.session_state.pop(FLASH_KEY, None)
    if flash is None:
        return
    outcome, key = flash
    if outcome == "saved":
        st.success(t(key), icon=":material/check:")
    else:
        st.error(t(key), icon=":material/error:")


def _write(user: dict, action: Callable[[sqlite3.Connection, str], object], done: str) -> NoReturn:
    """Run one write for the gymer; keep its outcome, or why it failed, for the next run."""
    try:
        with accounts.open_store(account.store_path()) as conn:
            action(conn, user["id"])
    except diary.DiaryError as error:
        _flash("error", error.code)
    except accounts.StoreUnavailable:
        _flash("error", "account.store_unavailable")
    except NotFound:
        _flash("error", "account.gone")
    _flash("saved", done)


def _read_own(user_id: str) -> tuple[list[dict], str | None, bool, dict] | None:
    """Return the recipes, their coach's name, whether there is a coach and the gymer's ratings."""
    with accounts.open_store(account.store_path()) as conn:
        if not accounts.has_profile_entries(conn, user_id):
            return None  # the recipes show only after the 18+ check on My profile
        found = store_recipes.list_recipes(conn, user_id)
        has_coach = any(
            row["status"] == "active" for row in users.list_relationships(conn, user_id)
        )
        name = None if not found else users.display_name_of(conn, user_id, found[0]["coach_id"])
        rated = {
            recipe["id"]: (
                ratings.can_rate(conn, user_id, recipe["id"]),
                ratings.own_rating(conn, user_id, recipe["id"]),
            )
            for recipe in found
        }
    return found, name, has_coach, rated


def _log_form(user: dict, recipe: dict, day: date, meal: str | None) -> None:
    """Show the portion picker, the recipe's foods at that portion and its Log button."""
    factor = st.select_slider(
        t("recipes.portion"),
        portions(),
        value=1.0,
        format_func=portion_format(),
        help=t("recipes.portion_help"),
        key=f"recipe_portion_{recipe['id']}",
    )
    show_foods(recipe_service.scaled(recipe["ingredients"], factor))
    if st.button(
        t("recipes.log"),
        type="primary",
        icon=":material/add:",
        key=f"recipe_log_{recipe['id']}",
        disabled=meal is None,
    ):
        _write(
            user,
            lambda conn, user_id: recipe_service.log_recipe(
                conn, user_id, recipe["id"], factor=factor, meal=meal, day=day
            ),
            "recipes.logged",
        )


def _rating(user: dict, recipe: dict, may_rate: bool, own: int | None) -> None:
    """Show the gymer's star rating of a recipe they logged, and what the coach sees of it."""
    if not may_rate:
        st.caption(t("recipes.rate_after_log"))
        return
    st.markdown(f"**{t('recipes.rate')}**")
    picked = st.feedback(
        "stars", key=f"recipe_rating_{recipe['id']}", default=None if own is None else own - 1
    )
    st.caption(t("recipes.rating_counts_note"))
    if picked is not None and picked + 1 != own:
        stars = picked + 1
        _write(
            user,
            lambda conn, user_id: recipe_service.rate_recipe(conn, user_id, recipe["id"], stars),
            "recipes.rated",
        )


def page() -> None:
    """Show the gymer's Recipes page: their current coach's recipes, to log and rate."""
    with header.main_column():
        header.show()
        account.store_notice()
        user = account.current_user()
        if user is None or user["role"] != "gymer":
            return  # not registered for them (views/navigation.py); never reached
        st.subheader(t("page.recipes"))
        _show_flash()
        try:
            found = _read_own(user["id"])
        except accounts.StoreUnavailable:
            st.error(t("account.store_unavailable"), icon=":material/error:")
            return
        except NotFound, accounts.AccountError:
            return  # the account was deleted in another tab: the next run shows the welcome page
        if found is None:
            st.info(t("recipes.profile_first"), icon=":material/person:")
            return
        recipes, coach_name, has_coach, rated = found
        if not has_coach:
            st.caption(t("recipes.no_coach"))
            return
        if not recipes:
            st.caption(t("recipes.none_gymer"))
            return
        # A display name is checked when it is chosen; escaped all the same (the other side's).
        st.markdown(t("recipes.gymer_intro", coach=chat.escape_markdown(coach_name)))
        st.info(t("recipes.gymer_not_checked"), icon=":material/info:")
        today = metrics.berlin_day()
        day_column, meal_column = st.columns([1, 2], vertical_alignment="bottom")
        day = day_column.date_input(
            t("recipes.day"),
            value=today,
            min_value=today - timedelta(days=config.DIARY_MAX_DAYS_BACK),
            max_value=today,
            format="YYYY-MM-DD",
            key="recipes_day",
        )
        meal = meal_column.segmented_control(
            t("recipes.meal"),
            tables.MEALS,
            format_func=label_of("my_data.meal"),
            key="recipes_meal",
            width="stretch",
        )
        for recipe in recipes:
            with st.expander(title(recipe), icon=":material/menu_book:"):
                _log_form(user, recipe, day, meal)
                show_steps(recipe["steps"])
                _rating(user, recipe, *rated[recipe["id"]])
        st.caption(f"{t('recipes.usda_note')} {t('usda.source_line')}")
