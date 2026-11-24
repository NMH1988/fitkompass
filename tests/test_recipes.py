"""Unit tests for the recipe service (T11.8): the coach's rows, logging, ratings and the steps.

The coach's rows become ingredients with the USDA table's nutrients; a recipe is saved, logged at a
portion and rated through the store, each refusal a fixed message code; and the coach's steps keep
their Markdown while every image and link is left as plain text.
"""

import re
from datetime import timedelta

import pytest

from src import config, diary, metrics
from src import recipes as recipe_service
from src.store import ratings, records, users
from src.store import recipes as store_recipes
from src.tools.food import Food

COACH = "coach-svc"
GYMER = "gym-svc"
OATS = Food(
    fdc_id=1,
    description="Oats",
    kcal=389.0,
    protein_g=16.9,
    carbohydrate_g=66.3,
    fat_g=6.9,
    fiber_g=10.6,
)
MILK = Food(fdc_id=2, description="Milk", kcal=61.0, protein_g=3.2, carbohydrate_g=4.8, fat_g=3.3)
TABLE = (OATS, MILK)
# The invisible character that breaks a bare link's start (checked in a browser on 2026-11-24).
WJ = recipe_service.WORD_JOINER


@pytest.fixture
def pair(store_conn):
    """A coach and their client with a saved profile; return the connection."""
    users.create_user(store_conn, COACH, "coach", "Coach")
    users.create_user(store_conn, GYMER, "gymer", "Gymer")
    users.start_relationship(store_conn, COACH, GYMER)
    records.add_profile_entry(
        store_conn, GYMER, height_cm=180, age=30, sex="male", activity="light", goal="maintain"
    )
    return store_conn


def _save(conn, **changes):
    """Save the coach's oats and milk recipe through the service; return its ID."""
    fields = {"name": "Oats", "steps": "Mix.", "rows": [("Oats", 80.0), ("Milk", 200.0)]}
    return recipe_service.save_recipe(conn, COACH, None, table=TABLE, **{**fields, **changes})


def _code(call) -> str:
    """Return the DiaryError code a call raises."""
    with pytest.raises(diary.DiaryError) as raised:
        call()
    return raised.value.code


# --- The coach's steps ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("steps", "shown"),
    [
        ("**Mix** the oats.\n\n- one\n- two", "**Mix** the oats.\n\n- one\n- two"),
        ("Look ![a pixel](https://example.invalid/p.png) here", "Look a pixel here"),
        ("See [my site](https://example.invalid/x) now", "See my site now"),
        ("See [my site][ref] now", "See my site now"),
        ("[ref]: https://example.invalid", "\\[ref\\]: https:" + WJ + "//example.invalid"),
        # A backslash is escaped too, so it can never undo an escape added here.
        ("Not \\[a link](https://example.invalid)", "Not \\\\a link"),
        ("Odd \\<b>", "Odd \\\\\\<b\\>"),
        ("Go to <https://example.invalid>", "Go to \\<https:" + WJ + "//example.invalid\\>"),
        ("Go to https://example.invalid", "Go to https:" + WJ + "//example.invalid"),
        ("Go to HTTP://example.invalid", "Go to HTTP:" + WJ + "//example.invalid"),
        ("Go to www.example.invalid", "Go to www" + WJ + ".example.invalid"),
        ("Go _www.example.invalid", "Go _www" + WJ + ".example.invalid"),
        ("Go *WWW.example.invalid", "Go *WWW" + WJ + ".example.invalid"),
        ("Mail me@example.invalid", "Mail me" + WJ + "@example.invalid"),
        ("<img src=x onerror=alert(1)>", "\\<img src=x onerror=alert(1)\\>"),
        ("Ratio 1:2, at 10:30", "Ratio 1:2, at 10:30"),
    ],
)
def test_the_steps_keep_markdown_but_no_image_or_link(steps, shown):
    """Formatting stays; images become their alt text, links plain text, bare links broken."""
    assert recipe_service.steps_markdown(steps) == shown


def test_a_nested_image_bracket_is_escaped_too():
    """An image the pattern misses keeps no unescaped "![" or "](" pair."""
    shown = recipe_service.steps_markdown("![a[b]c](https://example.invalid/p.png)")
    assert "![" not in shown
    # Every bracket is escaped, so no "](" or "][" can close a link.
    assert re.search(r"(?<!\\)[\[\]]", shown) is None


# --- Saving a recipe -----------------------------------------------------------------------------


def test_the_coach_s_rows_get_the_table_s_nutrients(pair):
    """Each food's nutrients are the table's per 100 g times its grams."""
    recipe_id = _save(pair)
    [saved] = store_recipes.list_recipes(pair, COACH)
    assert saved["id"] == recipe_id
    oats, milk = saved["ingredients"]
    assert (oats["fdc_id"], oats["kcal"], oats["fiber_g"]) == (1, pytest.approx(311.2), 8.48)
    assert (milk["fdc_id"], milk["kcal"], milk["fiber_g"]) == (2, 122.0, None)


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"name": "  "}, "recipes.name_needed"),
        ({"name": None}, "recipes.name_needed"),
        ({"steps": ""}, "recipes.steps_needed"),
        ({"name": "x" * (config.RECIPE_NAME_MAX_CHARS + 1)}, "recipes.too_long"),
        ({"steps": "x" * (config.RECIPE_STEPS_MAX_CHARS + 1)}, "recipes.too_long"),
        ({"rows": []}, "recipes.empty"),
        ({"rows": [("Oats", 80.0), ("Oats", 20.0)]}, "recipes.twice"),
        ({"rows": [("Not a food", 80.0)]}, "diary.food_needed"),
        ({"rows": [("Oats", 0.0)]}, "diary.grams_range"),
        ({"rows": [("Oats", 1.0), ("Milk", 1.0)]}, None),
    ],
)
def test_a_bad_recipe_gets_a_fixed_message_and_nothing_is_saved(pair, changes, code):
    """Each refusal is a DiaryError with the code of its message; the last case is valid."""
    if code is None:
        assert _save(pair, **changes)
        return
    assert _code(lambda: _save(pair, **changes)) == code
    assert store_recipes.list_recipes(pair, COACH) == []


def test_too_many_foods_is_refused(pair, monkeypatch):
    """More foods than config.MAX_RECIPE_INGREDIENTS."""
    monkeypatch.setattr(config, "MAX_RECIPE_INGREDIENTS", 1)
    assert _code(lambda: _save(pair)) == "recipes.full"


def test_too_many_recipes_is_refused(pair, monkeypatch):
    """A new recipe past config.MAX_RECIPES_PER_COACH."""
    monkeypatch.setattr(config, "MAX_RECIPES_PER_COACH", 1)
    _save(pair)
    assert _code(lambda: _save(pair)) == "recipes.too_many"


# --- Logging and rating --------------------------------------------------------------------------


def _log(conn, recipe_id, **changes):
    """Log the recipe for the gymer through the service; return the new IDs."""
    fields = {"factor": 1.0, "meal": "breakfast", "day": metrics.berlin_day(), **changes}
    return recipe_service.log_recipe(conn, GYMER, recipe_id, **fields)


@pytest.mark.parametrize("factor", [0.0, 0.2, 3.5, True, "1", None, float("nan")])
def test_a_factor_outside_the_range_is_refused(pair, factor):
    """Only a number in config.RECIPE_PORTION_RANGE."""
    assert _code(lambda: _log(pair, _save(pair), factor=factor)) == "recipes.portion_range"


def test_a_day_outside_the_diary_s_range_is_refused(pair):
    """The diary's own day rule: not in the future, not too far back."""
    tomorrow = metrics.berlin_day() + timedelta(days=1)
    assert _code(lambda: _log(pair, _save(pair), day=tomorrow)) == "diary.day_range"


def test_logging_needs_a_saved_profile(store_conn):
    """A gymer with no saved profile (no 18+ check) logs nothing."""
    users.create_user(store_conn, COACH, "coach", "Coach")
    users.create_user(store_conn, GYMER, "gymer", "Gymer")
    users.start_relationship(store_conn, COACH, GYMER)
    recipe_id = _save(store_conn)
    assert _code(lambda: _log(store_conn, recipe_id)) == "diary.profile_first"


def test_a_recipe_gone_before_the_log_is_a_fixed_message(pair):
    """Deleted between the read and the write: refused, nothing logged."""
    recipe_id = _save(pair)
    store_recipes.delete_recipe(pair, COACH, recipe_id)
    assert _code(lambda: _log(pair, recipe_id)) == "recipes.gone"
    assert records.list_meal_items(pair, GYMER, GYMER) == []


def test_a_portion_that_takes_a_food_out_of_range_is_a_fixed_message(pair):
    """A scaled food above the food log's maximum grams."""
    recipe_id = _save(pair, rows=[("Oats", 1000.0)])
    assert _code(lambda: _log(pair, recipe_id, factor=2.5)) == "recipes.scaled_grams"


def test_a_logged_recipe_is_marked_and_scaled(pair):
    """Each food at the portion, marked as from the recipe."""
    recipe_id = _save(pair)
    _log(pair, recipe_id, factor=0.5)
    items = records.list_meal_items(pair, GYMER, GYMER)
    assert [(i["grams"], i["from_recipe"]) for i in items] == [
        (40.0, recipe_id),
        (100.0, recipe_id),
    ]


@pytest.mark.parametrize("stars", [0, 6, 4.0, True, "4", None])
def test_stars_must_be_a_whole_number_from_one_to_five(pair, stars):
    """Anything else is a fixed message, never a store error."""
    recipe_id = _save(pair)
    _log(pair, recipe_id)
    assert _code(lambda: recipe_service.rate_recipe(pair, GYMER, recipe_id, stars)) == (
        "recipes.stars"
    )


def test_rating_a_recipe_not_logged_is_a_fixed_message(pair):
    """The store's NotFound becomes the cannot-rate message."""
    recipe_id = _save(pair)
    assert _code(lambda: recipe_service.rate_recipe(pair, GYMER, recipe_id, 4)) == (
        "recipes.cannot_rate"
    )
    _log(pair, recipe_id)
    recipe_service.rate_recipe(pair, GYMER, recipe_id, 4)
    assert ratings.own_rating(pair, GYMER, recipe_id) == 4


def test_scaled_and_totals():
    """The page's preview: every food times the factor, and the total of the four nutrients."""
    foods = [
        {"food_name": "A", "grams": 100.0, "kcal": 200.0, "protein_g": 10.0,
         "carbohydrate_g": 20.0, "fat_g": 5.0, "fiber_g": None},
        {"food_name": "B", "grams": 50.0, "kcal": 100.0, "protein_g": 2.0,
         "carbohydrate_g": 4.0, "fat_g": 1.0, "fiber_g": 3.0},
    ]  # fmt: skip
    half = recipe_service.scaled(foods, 0.5)
    assert [(f["grams"], f["kcal"], f["fiber_g"]) for f in half] == [
        (50.0, 100.0, None),
        (25.0, 50.0, 1.5),
    ]
    assert recipe_service.totals(half) == {
        "kcal": 150.0,
        "protein_g": 6.0,
        "carbohydrate_g": 12.0,
        "fat_g": 3.0,
    }
