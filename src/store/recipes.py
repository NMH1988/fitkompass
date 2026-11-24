"""The coach's recipe library (T11.8): recipes a coach writes and their current clients read.

A recipe is the coach's own content: a name, steps in their own words and USDA foods with grams,
each with the nutrients of its grams from the USDA table when it was saved. Only its coach saves,
edits or deletes it (`save_recipe()`, `delete_recipe()`), and every other case is the same
`NotFound`. An edit is a new version (the newest is the recipe), so no row is changed in place and
the recipe keeps its ID, its ratings and the marks on meals logged from it. Deleting a recipe
removes its versions, foods and ratings; the meal items gymers logged from it stay as they are,
their `from_recipe` mark pointing at an ID that is never given to another recipe (AUTOINCREMENT).

`list_recipes()` gives a coach their own recipes and a gymer the recipes of the coach they are
connected with now. The gymer's read checks the relationship itself, as `users.display_name_of()`
and the messages do: no scope, as a recipe holds none of the gymer's data, and not audited, as a
coach's read is (T11.8). A relationship's status is read as a value
(`ended_at`), never as a sharing filter, which only the `open_shares` view writes.
`recipe_for_client()` is the same check inside a caller's write transaction (logging a recipe,
rating it).
"""

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from src import config
from src.store import values
from src.store.access import NotFound, role_of
from src.store.db import checkpoint, transaction

NUTRIENTS: tuple[str, ...] = ("kcal", "protein_g", "carbohydrate_g", "fat_g")

_ADD_RECIPE = "INSERT INTO recipes (coach_id, created_at) VALUES (?, ?)"
_ADD_VERSION = """
INSERT INTO recipe_versions (recipe_id, name, steps, created_at) VALUES (?, ?, ?, ?)
"""
_ADD_INGREDIENT = """
INSERT INTO recipe_ingredients (
    version_id, fdc_id, food_name, grams, kcal, protein_g, carbohydrate_g, fat_g, fiber_g
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
_COUNT_OWN = "SELECT count(*) FROM recipes WHERE coach_id = ?"
_RECIPE = "SELECT id, coach_id, created_at FROM recipes WHERE id = ?"
_RECIPES_OF = "SELECT id, coach_id, created_at FROM recipes WHERE coach_id = ? ORDER BY id"
_NEWEST_VERSION = """
SELECT id, name, steps, created_at FROM recipe_versions
WHERE recipe_id = ? ORDER BY id DESC LIMIT 1
"""
_INGREDIENTS = """
SELECT fdc_id, food_name, grams, kcal, protein_g, carbohydrate_g, fat_g, fiber_g
FROM recipe_ingredients WHERE version_id = ? ORDER BY id
"""
# The client's relationships, their status read as a value (never a sharing filter).
_CLIENT_RELATIONSHIPS = (
    "SELECT coach_id, ended_at FROM coach_clients WHERE client_id = ? ORDER BY id"
)
# The delete, children before parents: the ratings, the versions' foods, the versions, the recipe.
_DELETE_RATINGS = "DELETE FROM recipe_ratings WHERE recipe_id = ?"
_DELETE_INGREDIENTS = """
DELETE FROM recipe_ingredients
WHERE version_id IN (SELECT id FROM recipe_versions WHERE recipe_id = ?)
"""
_DELETE_VERSIONS = "DELETE FROM recipe_versions WHERE recipe_id = ?"
_DELETE_RECIPE = "DELETE FROM recipes WHERE id = ? AND coach_id = ?"


class TooManyRecipes(ValueError):
    """Raised when a coach already keeps `config.MAX_RECIPES_PER_COACH` recipes."""


@dataclass(frozen=True)
class Ingredient:
    """One food of a recipe: the USDA food (its ID and name), the grams and their nutrients."""

    fdc_id: int
    food_name: str
    grams: float
    kcal: float
    protein_g: float
    carbohydrate_g: float
    fat_g: float
    fiber_g: float | None


def _checked_ingredients(ingredients: object) -> list[tuple]:
    """Return the ingredients as checked rows, refusing an empty, long or repeated list."""
    if isinstance(ingredients, str | bytes) or not isinstance(ingredients, Sequence):
        raise values.StoreValueError("ingredients", "must be a list of ingredients")
    if not 0 < len(ingredients) <= config.MAX_RECIPE_INGREDIENTS:
        raise values.StoreValueError("ingredients", "must hold one to the allowed number of foods")
    rows: list[tuple] = []
    seen: set[int] = set()
    for item in ingredients:
        if not isinstance(item, Ingredient):
            raise values.StoreValueError("ingredients", "must be a list of ingredients")
        fdc_id = values.whole_number(item.fdc_id, "fdc_id", minimum=1)
        if fdc_id in seen:
            raise values.StoreValueError("ingredients", "names a food twice")
        seen.add(fdc_id)
        rows.append(
            (
                fdc_id,
                values.text(item.food_name, "food_name"),
                values.in_range(
                    item.grams, "grams", (config.FOOD_MIN_GRAMS, config.FOOD_MAX_GRAMS)
                ),
                *(values.number(_nutrient(item, key), key) for key in NUTRIENTS),
                None if item.fiber_g is None else values.number(item.fiber_g, "fiber_g"),
            )
        )
    return rows


def _nutrient(item: Ingredient, key: str) -> object:
    """Return one of an ingredient's four nutrients by its column name."""
    # The store reaches no attribute by a name it was given (tests/test_store_sql_scan.py).
    match key:
        case "kcal":
            return item.kcal
        case "protein_g":
            return item.protein_g
        case "carbohydrate_g":
            return item.carbohydrate_g
        case "fat_g":
            return item.fat_g
    raise values.StoreValueError("nutrient", "is not one of the recipe's nutrients")


def save_recipe(
    conn: sqlite3.Connection,
    coach_id: str,
    recipe_id: int | None,
    *,
    name: str,
    steps: str,
    ingredients: Sequence[Ingredient],
) -> int:
    """Save a coach's new recipe (recipe_id None) or a new version of their own; return its ID."""
    # Every value is checked before the transaction, so a bad one writes nothing. Anyone but the
    # recipe's own coach (a gymer, a missing user, another coach, a recipe that is gone) gets the
    # same NotFound.
    try:
        values.user_id(coach_id)
    except values.StoreValueError:
        raise NotFound from None
    if recipe_id is not None and not values.is_row_id(recipe_id):
        raise NotFound
    checked_name = values.text(name, "name", config.RECIPE_NAME_MAX_CHARS)
    checked_steps = values.text(steps, "steps", config.RECIPE_STEPS_MAX_CHARS)
    rows = _checked_ingredients(ingredients)
    with transaction(conn):
        if role_of(conn, coach_id) != "coach":
            raise NotFound
        now = values.utc_text()
        if recipe_id is None:
            if conn.execute(_COUNT_OWN, (coach_id,)).fetchone()[0] >= config.MAX_RECIPES_PER_COACH:
                raise TooManyRecipes("too many recipes")
            recipe_id = conn.execute(_ADD_RECIPE, (coach_id, now)).lastrowid
        else:
            owner = conn.execute(_RECIPE, (recipe_id,)).fetchone()
            if owner is None or owner["coach_id"] != coach_id:
                raise NotFound
        version_id = conn.execute(
            _ADD_VERSION, (recipe_id, checked_name, checked_steps, now)
        ).lastrowid
        for row in rows:
            conn.execute(_ADD_INGREDIENT, (version_id, *row))
        return recipe_id


def delete_recipe(conn: sqlite3.Connection, coach_id: str, recipe_id: int) -> None:
    """Delete one of the coach's own recipes with its versions, foods and ratings; else NotFound."""
    # Meal items logged from it keep their from_recipe mark: its ID is never reused (AUTOINCREMENT).
    try:
        values.user_id(coach_id)
    except values.StoreValueError:
        raise NotFound from None
    if not values.is_row_id(recipe_id):
        raise NotFound
    with transaction(conn):
        owner = conn.execute(_RECIPE, (recipe_id,)).fetchone()
        if owner is None or owner["coach_id"] != coach_id or role_of(conn, coach_id) != "coach":
            raise NotFound
        conn.execute(_DELETE_RATINGS, (recipe_id,))
        conn.execute(_DELETE_INGREDIENTS, (recipe_id,))
        conn.execute(_DELETE_VERSIONS, (recipe_id,))
        conn.execute(_DELETE_RECIPE, (recipe_id, coach_id))
    # After the commit: the deleted ratings' earlier copies leave the write-ahead log too.
    checkpoint(conn)


def _current_coach(conn: sqlite3.Connection, client_id: str) -> str | None:
    """Return the coach the client is connected with now, or None."""
    for row in conn.execute(_CLIENT_RELATIONSHIPS, (client_id,)).fetchall():
        if row["ended_at"] is None:
            return row["coach_id"]
    return None


def _with_newest_version(conn: sqlite3.Connection, recipe: sqlite3.Row) -> dict:
    """Return a recipe with its newest version's name, steps, time and foods."""
    version = conn.execute(_NEWEST_VERSION, (recipe["id"],)).fetchone()
    ingredients = [dict(row) for row in conn.execute(_INGREDIENTS, (version["id"],))]
    return {
        "id": recipe["id"],
        "coach_id": recipe["coach_id"],
        "created_at": recipe["created_at"],
        "version_id": version["id"],
        "name": version["name"],
        "steps": version["steps"],
        "updated_at": version["created_at"],
        "ingredients": ingredients,
    }


def list_recipes(conn: sqlite3.Connection, actor_id: str) -> list[dict]:
    """Return a coach's own recipes, or a gymer's current coach's; each at its newest version."""
    try:
        values.user_id(actor_id)
    except values.StoreValueError:
        raise NotFound from None
    with transaction(conn):
        role = role_of(conn, actor_id)
        if role is None:
            raise NotFound
        coach_id = actor_id if role == "coach" else _current_coach(conn, actor_id)
        if coach_id is None:
            return []
        found = conn.execute(_RECIPES_OF, (coach_id,)).fetchall()
        return [_with_newest_version(conn, recipe) for recipe in found]


def recipe_for_client(conn: sqlite3.Connection, user_id: str, recipe_id: object) -> dict | None:
    """Return a recipe at its newest version if it is the gymer's current coach's, else None."""
    # Runs inside the caller's write transaction (records.add_recipe_items(), ratings); opens none.
    if role_of(conn, user_id) != "gymer" or not values.is_row_id(recipe_id):
        return None
    owner = conn.execute(_RECIPE, (recipe_id,)).fetchone()
    if owner is None or owner["coach_id"] != _current_coach(conn, user_id):
        return None
    return _with_newest_version(conn, owner)
