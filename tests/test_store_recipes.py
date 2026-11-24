"""Store tests for the coach's recipe library and the clients' ratings (T11.8, AC-48).

A coach saves recipes (an edit is a new version that keeps the recipe's ID), deletes one with its
versions, foods and ratings, and keeps the limits in config. A current client logs a recipe scaled
by a factor, each food marked `from_recipe`; an edit keeps the mark only for the same food. A client
who logged it rates it, the newest rating counting; the coach sees only the average and the count of
clients who share nutrition, from `config.RATING_MIN_RATERS`. Who may do what is tested in
tests/test_store_access.py; here, what each does, the export and the delete.
"""

import json
from datetime import date

import pytest

from src import config
from src.store import my_data, ratings, recipes, records, users, values
from src.store.access import NotFound
from tests.store_world import no_threads

COACH = "coach-r"
OTHER_COACH = "coach-s"
CLIENTS = ("gym-r1", "gym-r2", "gym-r3", "gym-r4")
DAY = date(2026, 11, 20)
OATS = recipes.Ingredient(1001, "Oats, rolled", 80.0, 304.8, 10.6, 54.1, 5.2, 8.0)
MILK = recipes.Ingredient(1002, "Milk, whole", 200.0, 122.0, 6.4, 9.6, 6.6, None)
CANARY = "CANARY-RECIPE"


@pytest.fixture
def world(store_conn):
    """Create a coach with four clients sharing nutrition and another coach; return the threads."""
    users.create_user(store_conn, COACH, "coach", "Coach R")
    users.create_user(store_conn, OTHER_COACH, "coach", "Coach S")
    threads = {}
    for client in CLIENTS:
        users.create_user(store_conn, client, "gymer", client)
        threads[client] = users.start_relationship(store_conn, COACH, client)
        users.set_consent(store_conn, client, threads[client], "nutrition", True)
    return threads


def _save(conn, recipe_id=None, *, name="Overnight oats", ingredients=(OATS, MILK)):
    """Save a recipe (or a new version of one) as the coach; return its ID."""
    return recipes.save_recipe(
        conn,
        COACH,
        recipe_id,
        name=name,
        steps="Mix and **soak** overnight.",
        ingredients=ingredients,
    )


def _log(conn, client, recipe_id, factor=1.0):
    """Log the recipe for a client at a factor; return the new items' IDs."""
    return records.add_recipe_items(
        conn, client, recipe_id, consumed_on=DAY, meal="breakfast", factor=factor
    )


def _items(conn, client):
    """Return a client's meal items, read as the client."""
    return records.list_meal_items(conn, client, client)


def _count(conn, table):
    """Return how many rows a table holds (test-only SQL with the test's own table names)."""
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


# --- Saving, editing and deleting a recipe ------------------------------------------------------


def test_a_saved_recipe_lists_with_its_foods_and_nutrients(store_conn, world):
    """The coach's recipe lists with its name, steps and each food's grams and nutrients."""
    recipe_id = _save(store_conn)
    [found] = recipes.list_recipes(store_conn, COACH)
    assert found["id"] == recipe_id and found["coach_id"] == COACH
    assert (found["name"], found["steps"]) == ("Overnight oats", "Mix and **soak** overnight.")
    assert [(i["fdc_id"], i["grams"], i["kcal"], i["fiber_g"]) for i in found["ingredients"]] == [
        (1001, 80.0, 304.8, 8.0),
        (1002, 200.0, 122.0, None),
    ]


def test_an_edit_is_a_new_version_that_keeps_the_id(store_conn, world):
    """Saving with the recipe's ID adds a version; the list shows the newest, both rows are kept."""
    recipe_id = _save(store_conn)
    assert _save(store_conn, recipe_id, name="Oats with milk", ingredients=(OATS,)) == recipe_id
    [found] = recipes.list_recipes(store_conn, COACH)
    assert found["name"] == "Oats with milk"
    assert [i["fdc_id"] for i in found["ingredients"]] == [1001]
    assert _count(store_conn, "recipes") == 1
    assert _count(store_conn, "recipe_versions") == 2
    assert _count(store_conn, "recipe_ingredients") == 3


def test_another_coach_s_recipes_stay_apart(store_conn, world):
    """Each coach lists only their own recipes; a client lists only their coach's."""
    _save(store_conn)
    recipes.save_recipe(
        store_conn, OTHER_COACH, None, name="Rice bowl", steps="Cook.", ingredients=[OATS]
    )
    assert [r["name"] for r in recipes.list_recipes(store_conn, COACH)] == ["Overnight oats"]
    assert [r["name"] for r in recipes.list_recipes(store_conn, OTHER_COACH)] == ["Rice bowl"]
    assert [r["name"] for r in recipes.list_recipes(store_conn, CLIENTS[0])] == ["Overnight oats"]


@pytest.mark.parametrize(
    ("field", "change"),
    [
        ("name", {"name": CANARY + "x" * config.RECIPE_NAME_MAX_CHARS}),
        ("name", {"name": "   "}),
        ("steps", {"steps": CANARY + "x" * config.RECIPE_STEPS_MAX_CHARS}),
        ("steps", {"steps": ""}),
        ("ingredients", {"ingredients": []}),
        ("ingredients", {"ingredients": [OATS] * 2}),
        ("ingredients", {"ingredients": "oats"}),
        ("ingredients", {"ingredients": [("oats", 80.0)]}),
        (
            "ingredients",
            {
                "ingredients": [
                    recipes.Ingredient(n, "Food", 10.0, 1.0, 0.0, 0.0, 0.0, None)
                    for n in range(1, config.MAX_RECIPE_INGREDIENTS + 2)
                ]
            },
        ),
        ("grams", {"ingredients": [recipes.Ingredient(1, "Food", 0.0, 1.0, 0, 0, 0, None)]}),
        (
            "grams",
            {
                "ingredients": [
                    recipes.Ingredient(1, "Food", config.FOOD_MAX_GRAMS + 1, 1.0, 0, 0, 0, None)
                ]
            },
        ),
        ("kcal", {"ingredients": [recipes.Ingredient(1, "Food", 10.0, -1.0, 0, 0, 0, None)]}),
        ("fiber_g", {"ingredients": [recipes.Ingredient(1, "Food", 10.0, 1.0, 0, 0, 0, -2.0)]}),
        ("fdc_id", {"ingredients": [recipes.Ingredient(0, "Food", 10.0, 1.0, 0, 0, 0, None)]}),
    ],
)
def test_a_bad_recipe_is_refused_by_name_and_nothing_is_written(store_conn, world, field, change):
    """Each bad value is refused before writing; the error names the field, never the value."""
    fields = {"name": "Oats", "steps": "Soak.", "ingredients": [OATS], **change}
    with pytest.raises(values.StoreValueError) as raised:
        recipes.save_recipe(store_conn, COACH, None, **fields)
    assert field in str(raised.value) and CANARY not in str(raised.value)
    assert _count(store_conn, "recipes") == 0


def test_a_coach_keeps_at_most_the_configured_number_of_recipes(store_conn, world, monkeypatch):
    """A new recipe past the limit is refused; an edit of a kept one still works."""
    monkeypatch.setattr(config, "MAX_RECIPES_PER_COACH", 2)
    first = _save(store_conn)
    _save(store_conn)
    with pytest.raises(recipes.TooManyRecipes):
        _save(store_conn)
    assert _save(store_conn, first, name="Edited") == first
    assert _count(store_conn, "recipes") == 2


def test_deleting_a_recipe_removes_its_versions_foods_and_ratings_but_not_logged_meals(
    store_conn, world
):
    """The client's logged meals keep their mark; a new recipe never gets the deleted one's ID."""
    recipe_id = _save(store_conn)
    _save(store_conn, recipe_id, name="Edited")
    _log(store_conn, CLIENTS[0], recipe_id)
    ratings.rate_recipe(store_conn, CLIENTS[0], recipe_id, 5)
    recipes.delete_recipe(store_conn, COACH, recipe_id)
    for table in ("recipes", "recipe_versions", "recipe_ingredients", "recipe_ratings"):
        assert _count(store_conn, table) == 0
    assert [item["from_recipe"] for item in _items(store_conn, CLIENTS[0])] == [recipe_id] * 2
    assert _save(store_conn) > recipe_id


def test_recipe_writes_and_reads_leave_no_audit_row(store_conn, world):
    """The coach's own content and the clients' reads of it are not audited."""
    recipe_id = _save(store_conn)
    recipes.list_recipes(store_conn, CLIENTS[0])
    _log(store_conn, CLIENTS[0], recipe_id)
    ratings.rate_recipe(store_conn, CLIENTS[0], recipe_id, 4)
    ratings.rating_summaries(store_conn, COACH)
    recipes.delete_recipe(store_conn, COACH, recipe_id)
    assert _count(store_conn, "audit_log") == 0


# --- Logging a recipe ---------------------------------------------------------------------------


def test_a_logged_recipe_is_one_marked_item_per_food_at_its_grams(store_conn, world):
    """At factor 1 each food is logged with the recipe's grams and nutrients and the mark."""
    recipe_id = _save(store_conn)
    ids = _log(store_conn, CLIENTS[0], recipe_id)
    found = _items(store_conn, CLIENTS[0])
    assert [item["id"] for item in found] == ids
    assert [
        (i["fdc_id"], i["grams"], i["kcal"], i["fiber_g"], i["from_recipe"], i["from_suggestion"])
        for i in found
    ] == [(1001, 80.0, 304.8, 8.0, recipe_id, 0), (1002, 200.0, 122.0, None, recipe_id, 0)]
    assert {(i["consumed_on"], i["meal"]) for i in found} == {("2026-11-20", "breakfast")}


@pytest.mark.parametrize("factor", [0.25, 0.5, 1.5, 3.0])
def test_a_factor_scales_every_food_s_grams_and_nutrients(store_conn, world, factor):
    """Every food's grams and nutrients are the recipe's times the factor."""
    recipe_id = _save(store_conn)
    _log(store_conn, CLIENTS[0], recipe_id, factor)
    oats, milk = _items(store_conn, CLIENTS[0])
    assert oats["grams"] == pytest.approx(80.0 * factor)
    assert oats["protein_g"] == pytest.approx(10.6 * factor)
    assert oats["fiber_g"] == pytest.approx(8.0 * factor)
    assert milk["kcal"] == pytest.approx(122.0 * factor)
    assert milk["fiber_g"] is None


@pytest.mark.parametrize("factor", [0.0, 0.2, 3.25, -1.0, float("nan"), "1", True, None])
def test_a_factor_outside_the_range_is_refused_and_nothing_is_logged(store_conn, world, factor):
    """A factor outside config.RECIPE_PORTION_RANGE, or not a number, writes nothing."""
    recipe_id = _save(store_conn)
    with pytest.raises(values.StoreValueError, match="factor"):
        _log(store_conn, CLIENTS[0], recipe_id, factor)
    assert _items(store_conn, CLIENTS[0]) == []


def test_a_scaled_food_outside_the_gram_range_writes_nothing(store_conn, world):
    """A food whose scaled grams pass the food log's maximum refuses the whole recipe."""
    big = recipes.Ingredient(1003, "Water", 1500.0, 0.0, 0.0, 0.0, 0.0, None)
    recipe_id = _save(store_conn, ingredients=(OATS, big))
    with pytest.raises(values.StoreValueError, match="grams"):
        _log(store_conn, CLIENTS[0], recipe_id, 2.0)
    assert _items(store_conn, CLIENTS[0]) == []


def test_a_recipe_is_logged_at_its_newest_version(store_conn, world):
    """After an edit, logging uses the newest version's foods."""
    recipe_id = _save(store_conn)
    _save(store_conn, recipe_id, ingredients=(MILK,))
    _log(store_conn, CLIENTS[0], recipe_id)
    assert [item["fdc_id"] for item in _items(store_conn, CLIENTS[0])] == [1002]


def _edit(conn, client, item, fdc_id, grams):
    """Replace a client's meal item with a food and grams; return the new item's ID."""
    return records.replace_meal_item(
        conn,
        client,
        item["id"],
        consumed_on=DAY,
        meal="lunch",
        fdc_id=fdc_id,
        food_name="A food",
        grams=grams,
        kcal=100.0,
        protein_g=1.0,
        carbohydrate_g=1.0,
        fat_g=1.0,
        fiber_g=None,
    )


def test_an_edit_keeps_the_mark_only_while_the_food_stays_the_same(store_conn, world):
    """New grams or a new meal slot keep the mark; another food drops it."""
    recipe_id = _save(store_conn)
    _log(store_conn, CLIENTS[0], recipe_id)
    oats, milk = _items(store_conn, CLIENTS[0])
    _edit(store_conn, CLIENTS[0], oats, 1001, 60.0)
    _edit(store_conn, CLIENTS[0], milk, 2002, 150.0)
    marks = {item["fdc_id"]: item["from_recipe"] for item in _items(store_conn, CLIENTS[0])}
    assert marks == {1001: recipe_id, 2002: None}


def test_a_plain_meal_item_has_no_recipe_mark(store_conn, world):
    """A food logged by hand is not marked."""
    records.add_meal_item(
        store_conn,
        CLIENTS[0],
        consumed_on=DAY,
        meal="lunch",
        fdc_id=1001,
        food_name="Oats",
        grams=50.0,
        kcal=190.0,
        protein_g=6.6,
        carbohydrate_g=33.8,
        fat_g=3.3,
        fiber_g=5.0,
    )
    assert [item["from_recipe"] for item in _items(store_conn, CLIENTS[0])] == [None]


# --- Ratings ------------------------------------------------------------------------------------


def _rated(conn, recipe_id, *stars_by_client):
    """Log the recipe and rate it for the first clients, one star count each."""
    for client, stars in zip(CLIENTS, stars_by_client, strict=False):
        _log(conn, client, recipe_id)
        ratings.rate_recipe(conn, client, recipe_id, stars)


def test_a_new_rating_is_a_new_row_and_the_newest_counts(store_conn, world):
    """A client's second rating replaces the first in the average; both rows are kept."""
    recipe_id = _save(store_conn)
    _rated(store_conn, recipe_id, 2, 4, 5)
    assert ratings.own_rating(store_conn, CLIENTS[0], recipe_id) == 2
    ratings.rate_recipe(store_conn, CLIENTS[0], recipe_id, 5)
    assert ratings.own_rating(store_conn, CLIENTS[0], recipe_id) == 5
    assert _count(store_conn, "recipe_ratings") == 4
    assert ratings.rating_summaries(store_conn, COACH) == {recipe_id: (pytest.approx(14 / 3), 3)}


def test_the_coach_sees_the_average_from_the_minimum_and_nothing_below_it(store_conn, world):
    """At config.RATING_MIN_RATERS raters the average and count show; one below, neither does."""
    assert config.RATING_MIN_RATERS == 3
    recipe_id = _save(store_conn)
    _rated(store_conn, recipe_id, 3, 4)
    assert ratings.rating_summaries(store_conn, COACH) == {}
    _rated(store_conn, recipe_id, 3, 4, 5)
    assert ratings.rating_summaries(store_conn, COACH) == {recipe_id: (4.0, 3)}


def test_a_rating_of_a_client_who_stopped_sharing_nutrition_is_not_counted(store_conn, world):
    """Three raters, then one turns nutrition off: the count drops below the minimum."""
    recipe_id = _save(store_conn)
    _rated(store_conn, recipe_id, 3, 4, 5)
    users.set_consent(store_conn, CLIENTS[2], world[CLIENTS[2]], "nutrition", False)
    assert ratings.rating_summaries(store_conn, COACH) == {}
    users.set_consent(store_conn, CLIENTS[2], world[CLIENTS[2]], "nutrition", True)
    assert ratings.rating_summaries(store_conn, COACH) == {recipe_id: (4.0, 3)}


def test_a_client_who_does_not_share_nutrition_still_rates_but_is_not_counted(store_conn, world):
    """The rating is stored and is the client's own; the coach's count leaves it out."""
    recipe_id = _save(store_conn)
    users.set_consent(store_conn, CLIENTS[3], world[CLIENTS[3]], "nutrition", False)
    _rated(store_conn, recipe_id, 3, 4)
    _log(store_conn, CLIENTS[3], recipe_id)
    ratings.rate_recipe(store_conn, CLIENTS[3], recipe_id, 5)
    assert ratings.own_rating(store_conn, CLIENTS[3], recipe_id) == 5
    assert ratings.rating_summaries(store_conn, COACH) == {}


def test_a_former_client_s_rating_is_not_counted(store_conn, world):
    """A rater whose relationship ended no longer counts."""
    recipe_id = _save(store_conn)
    _rated(store_conn, recipe_id, 3, 4, 5)
    users.end_relationship(store_conn, CLIENTS[1], world[CLIENTS[1]])
    assert ratings.rating_summaries(store_conn, COACH) == {}


def test_summaries_are_per_recipe_and_only_the_coach_s_own(store_conn, world):
    """Ratings of one recipe never count for another, and another coach sees none of them."""
    first = _save(store_conn)
    second = _save(store_conn, name="Second")
    _rated(store_conn, first, 5, 5, 5)
    _rated(store_conn, second, 1, 2)
    assert ratings.rating_summaries(store_conn, COACH) == {first: (5.0, 3)}
    assert ratings.rating_summaries(store_conn, OTHER_COACH) == {}


@pytest.mark.parametrize("stars", [0, 6, 2.5, "5", True, None])
def test_a_rating_outside_one_to_five_stars_is_refused(store_conn, world, stars):
    """Stars must be a whole number from 1 to 5; nothing is written."""
    recipe_id = _save(store_conn)
    _log(store_conn, CLIENTS[0], recipe_id)
    with pytest.raises(values.StoreValueError, match="stars"):
        ratings.rate_recipe(store_conn, CLIENTS[0], recipe_id, stars)
    assert _count(store_conn, "recipe_ratings") == 0


def test_own_rating_reads_only_the_user_s_own(store_conn, world):
    """Another client's rating is never read as one's own."""
    recipe_id = _save(store_conn)
    _rated(store_conn, recipe_id, 4)
    assert ratings.own_rating(store_conn, CLIENTS[1], recipe_id) is None
    assert ratings.own_rating(store_conn, CLIENTS[0], 9999) is None
    with pytest.raises(NotFound):
        ratings.own_rating(store_conn, "no-such-user", recipe_id)


# --- Export and delete --------------------------------------------------------------------------


def _export(conn, user_id):
    """Return a user's export as a dict."""
    return json.loads(my_data.export_user_data(conn, user_id))


def test_the_coach_s_export_holds_their_recipes_but_no_ratings(store_conn, world):
    """Every version and food of the coach's recipes; the clients' ratings stay theirs."""
    recipe_id = _save(store_conn)
    _save(store_conn, recipe_id, name="Edited")
    _rated(store_conn, recipe_id, 4)
    exported = _export(store_conn, COACH)
    assert [r["id"] for r in exported["recipes"]] == [recipe_id]
    assert [v["name"] for v in exported["recipe_versions"]] == ["Overnight oats", "Edited"]
    assert len(exported["recipe_ingredients"]) == 4
    assert exported["recipe_ratings"] == []


def test_the_gymer_s_export_holds_their_ratings_and_marks_but_not_the_recipes(store_conn, world):
    """The client's own ratings and marked meal items; the coach's recipes are the coach's."""
    recipe_id = _save(store_conn)
    _rated(store_conn, recipe_id, 4, 2)
    exported = _export(store_conn, CLIENTS[0])
    assert [(r["recipe_id"], r["stars"]) for r in exported["recipe_ratings"]] == [(recipe_id, 4)]
    assert [m["from_recipe"] for m in exported["meal_items"]] == [recipe_id] * 2
    assert exported["recipes"] == exported["recipe_versions"] == []


def test_the_coach_s_delete_leaves_the_gymers_logs_and_marks(store_conn, world):
    """The recipes and their ratings go; each client's meal items and marks stay as they were."""
    recipe_id = _save(store_conn)
    _rated(store_conn, recipe_id, 4, 5)
    before = {client: _items(store_conn, client) for client in CLIENTS[:2]}
    my_data.delete_user_data(store_conn, COACH, no_threads)
    for table in ("recipes", "recipe_versions", "recipe_ingredients", "recipe_ratings"):
        assert _count(store_conn, table) == 0
    assert {client: _items(store_conn, client) for client in CLIENTS[:2]} == before


def test_the_gymer_s_delete_removes_their_ratings_and_keeps_the_recipe(store_conn, world):
    """The client's ratings go with their data; the recipe and others' ratings stay."""
    recipe_id = _save(store_conn)
    _rated(store_conn, recipe_id, 4, 5)
    my_data.delete_user_data(store_conn, CLIENTS[0], no_threads)
    assert [r["id"] for r in recipes.list_recipes(store_conn, COACH)] == [recipe_id]
    assert ratings.own_rating(store_conn, CLIENTS[1], recipe_id) == 5
    assert _count(store_conn, "recipe_ratings") == 1


def test_a_recipe_after_the_coach_s_delete_never_reuses_an_id(store_conn, world):
    """A coach who signs up again starts with recipe IDs the old marks never point at."""
    recipe_id = _save(store_conn)
    my_data.delete_user_data(store_conn, COACH, no_threads)
    users.create_user(store_conn, COACH, "coach", "Coach R")
    assert _save(store_conn) > recipe_id
