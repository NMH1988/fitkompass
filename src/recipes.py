"""The coach's recipe library (T11.8): the coach's rows to stored foods, logging, ratings, steps.

The store keeps the recipes and ratings and decides who may write and read them
(`src/store/recipes.py`, `src/store/ratings.py`); this module turns the coach's rows (a USDA food
name and grams) into the store's ingredients with the nutrients of their grams from the USDA table,
logs a recipe for a gymer at a portion they choose, and turns the coach's steps into Markdown that
loads nothing and links nowhere. Foods are the USDA table's own names (T4.8), looked up exactly, as
the diary does. Nothing here reaches a model; T11.9 logs a coach's recipe through `log_recipe()`.

A recipe is a dish, not a day's intake, so the calorie floor does not apply to it. The app checks
neither a recipe's allergens nor the coach's qualifications, and the pages say so.

Each error is a `diary.DiaryError` whose code is the i18n key of its message, which never repeats
what was typed or stored.
"""

import re
import sqlite3
from collections.abc import Iterable, Sequence

from src import config, diary, metrics
from src.store import ratings, recipes, records
from src.store.access import NotFound
from src.store.values import StoreValueError
from src.tools.food import Food

NUTRIENTS = (*recipes.NUTRIENTS, "fiber_g")

# A Markdown image (![alt](url) or ![alt][ref]) and a link ([text](url), [text][ref] or [text][]):
# only the alt text or the link's text stays, so the coach's steps load nothing from another server
# and send no one anywhere (a video link is T11.11's, checked when it is saved).
_MARKDOWN_IMAGE = re.compile(r"!\[([^\[\]]*)\](?:\((?:[^()]|\([^()]*\))*\)|\[[^\[\]]*\])")
_MARKDOWN_LINK = re.compile(r"\[([^\[\]]*)\](?:\((?:[^()]|\([^()]*\))*\)|\[[^\[\]]*\])")
# What would still make an image, a link or HTML: a backslash (which could undo an escape added
# here), a bracket (a reference definition, an image or link the patterns missed, such as one with
# nested brackets) and an angle bracket (an autolink <https://...>, HTML), each escaped with a
# backslash; and the bare links GitHub-flavoured Markdown turns into links whatever is escaped (a
# scheme's "://", "www.", an e-mail's "@", checked in a browser on 2026-11-24), each broken by an
# invisible word joiner. All in one pass, so it shows as typed and no escape is undone.
# "www" has no word boundary before it: GitHub-flavoured Markdown also links "_www." and the like.
_LINK_SPECIAL = re.compile(r"[\\\[\]<>]|(?<=[A-Za-z]):(?=//)|(?<=www)\.|@", re.IGNORECASE)
WORD_JOINER = "⁠"


def _neutralised(found: re.Match) -> str:
    """Return one special character escaped, or a bare link's start broken by a word joiner."""
    character = found.group(0)
    if character == ":":
        return ":" + WORD_JOINER
    if character in ".@":
        return WORD_JOINER + character
    return "\\" + character


def steps_markdown(steps: str) -> str:
    """Return the coach's steps as Markdown with every image and link left as plain text."""
    without_images = _MARKDOWN_IMAGE.sub(lambda image: image.group(1), steps)
    without_links = _MARKDOWN_LINK.sub(lambda link: link.group(1), without_images)
    return _LINK_SPECIAL.sub(_neutralised, without_links)


def ingredient(
    name: object, grams: object, table: Sequence[Food] | None = None
) -> recipes.Ingredient:
    """Return one coach's row as the store's ingredient, with the nutrients of its grams."""
    food = diary.find_food(name, table)
    checked_grams = diary.check_grams(grams)
    nutrients = diary.snapshot(food, checked_grams)
    return recipes.Ingredient(
        fdc_id=food.fdc_id,
        food_name=food.description,
        grams=checked_grams,
        **{key: nutrients[key] for key in NUTRIENTS},
    )


def build_ingredients(
    rows: Iterable[tuple[object, object]], table: Sequence[Food] | None = None
) -> list[recipes.Ingredient]:
    """Return the coach's rows (food name, grams) as the store's ingredients."""
    items = [ingredient(name, grams, table) for name, grams in rows]
    ids = [item.fdc_id for item in items]
    if len(set(ids)) != len(ids):
        raise diary.DiaryError("recipes.twice")
    return items


def _checked_text(value: object, limit: int, needed: str) -> str:
    """Return the coach's name or steps if they hold text within the limit."""
    if not isinstance(value, str) or not value.strip():
        raise diary.DiaryError(needed)
    if len(value) > limit:
        raise diary.DiaryError("recipes.too_long")
    return value


def save_recipe(
    conn: sqlite3.Connection,
    coach_id: str,
    recipe_id: int | None,
    *,
    name: object,
    steps: object,
    rows: Iterable[tuple[object, object]],
    table: Sequence[Food] | None = None,
) -> int:
    """Save the coach's new recipe, or a new version of theirs (the store checks); return its ID."""
    checked_name = _checked_text(name, config.RECIPE_NAME_MAX_CHARS, "recipes.name_needed")
    checked_steps = _checked_text(steps, config.RECIPE_STEPS_MAX_CHARS, "recipes.steps_needed")
    items = build_ingredients(rows, table)
    if not items:
        raise diary.DiaryError("recipes.empty")
    if len(items) > config.MAX_RECIPE_INGREDIENTS:
        raise diary.DiaryError("recipes.full")
    try:
        return recipes.save_recipe(
            conn, coach_id, recipe_id, name=checked_name, steps=checked_steps, ingredients=items
        )
    except recipes.TooManyRecipes:
        raise diary.DiaryError("recipes.too_many") from None


def check_factor(factor: object) -> float:
    """Return the portion factor if it is a number in config.RECIPE_PORTION_RANGE."""
    low, high = config.RECIPE_PORTION_RANGE
    # A number only (no strings or booleans); NaN fails both comparisons.
    if isinstance(factor, bool) or not isinstance(factor, int | float) or not low <= factor <= high:
        raise diary.DiaryError("recipes.portion_range")
    return float(factor)


def log_recipe(
    conn: sqlite3.Connection,
    user_id: str,
    recipe_id: object,
    *,
    factor: object,
    meal: object,
    day: object,
) -> list[int]:
    """Log a recipe of the gymer's current coach at a portion; return the new entries' IDs."""
    # The store checks again, in its write transaction, that the recipe is the current coach's.
    checked_factor = check_factor(factor)
    checked_meal = diary.check_meal(meal)
    checked_day = diary.check_day(day, metrics.berlin_day())
    diary.check_profile_saved(conn, user_id)
    try:
        return records.add_recipe_items(
            conn,
            user_id,
            recipe_id,
            consumed_on=checked_day,
            meal=checked_meal,
            factor=checked_factor,
        )
    except NotFound:
        # The recipe was deleted, or the relationship ended, between the read and the write.
        raise diary.DiaryError("recipes.gone") from None
    except StoreValueError:
        # A food whose scaled grams leave the food log's range.
        raise diary.DiaryError("recipes.scaled_grams") from None


def rate_recipe(conn: sqlite3.Connection, user_id: str, recipe_id: object, stars: object) -> int:
    """Save the gymer's rating of a recipe they logged; return its ID."""
    # A whole number from 1 to 5 only: not a bool or a float that equals one.
    if type(stars) is not int or stars not in ratings.STARS:
        raise diary.DiaryError("recipes.stars")
    try:
        return ratings.rate_recipe(conn, user_id, recipe_id, stars)
    except NotFound:
        raise diary.DiaryError("recipes.cannot_rate") from None


def scaled(ingredients: Sequence[dict], factor: float) -> list[dict]:
    """Return the recipe's foods with their grams and nutrients times the factor."""
    return [
        {
            **food,
            "grams": food["grams"] * factor,
            **{
                key: None if food[key] is None else food[key] * factor
                for key in NUTRIENTS
                if key in food
            },
        }
        for food in ingredients
    ]


def totals(ingredients: Sequence[dict]) -> dict[str, float]:
    """Return the foods' total energy and macronutrients."""
    return {key: sum(food[key] for food in ingredients) for key in recipes.NUTRIENTS}
