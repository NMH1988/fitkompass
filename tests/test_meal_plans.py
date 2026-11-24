"""The coach's meal plan service (T11.7): the rows, their nutrients, the floor and the totals.

Not the chat's `evaluate_meal_plan` tool (T4.5), whose tests are in `tests/test_meal_plan.py`.
"""

import pytest

from src import config, diary, meal_plans
from src.store import access
from src.store import meal_plans as store_plans
from src.tools.food import Food
from tests import store_world as world

OATS = Food(
    fdc_id=11,
    description="Oats, made-up",
    kcal=380.0,
    protein_g=13.0,
    carbohydrate_g=68.0,
    fat_g=6.5,
    fiber_g=10.0,
)
RICE = Food(
    fdc_id=12,
    description="Rice, made-up",
    kcal=130.0,
    protein_g=2.7,
    carbohydrate_g=28.0,
    fat_g=0.3,
    fiber_g=None,
)
TABLE = (OATS, RICE)
# 200 g oats (760 kcal) and 400 g rice (520 kcal): 1280 kcal, above the floor.
DAY = [("breakfast", "Oats, made-up", 200), ("lunch", "Rice, made-up", 400)]


@pytest.fixture
def relationships(store_conn):
    """Build the made-up world in the test's store and return its relationship IDs."""
    return world.build(store_conn)


def test_the_stored_nutrients_come_from_the_table_not_the_caller(store_conn, relationships):
    """Only (meal, name, grams) go in: the kcal stored is the table's, whatever a draft held."""
    richer = (OATS.model_copy(update={"kcal": 900.0}), RICE)
    meal_plans.save_meal_plan(store_conn, world.COACH_A, world.SHARED, DAY, richer)
    plan = store_plans.current_meal_plan(store_conn, world.SHARED, world.SHARED)
    assert plan["items"][0]["kcal"] == 1800.0  # 200 g at the given table's 900 kcal per 100 g


def test_removing_a_plan_already_removed_adds_no_plan(store_conn, relationships):
    """A second removal (another tab, say) adds no empty plan and so no second notification."""
    meal_plans.save_meal_plan(store_conn, world.COACH_A, world.SHARED, DAY, TABLE)
    assert meal_plans.remove_meal_plan(store_conn, world.COACH_A, world.SHARED) is not None
    assert meal_plans.remove_meal_plan(store_conn, world.COACH_A, world.SHARED) is None
    assert store_conn.execute("SELECT count(*) FROM meal_plans").fetchone()[0] == 2


def test_a_row_becomes_a_planned_food_with_the_nutrients_of_its_grams():
    """The table's ID and name, and each nutrient per 100 g times the grams / 100."""
    item = meal_plans.planned_food("lunch", "Rice, made-up", 150, TABLE)
    assert item == store_plans.PlannedFood(
        "lunch", 12, "Rice, made-up", 150.0, 195.0, 2.7 * 1.5, 42.0, 0.3 * 1.5
    )


@pytest.mark.parametrize(
    ("row", "code"),
    [
        (("lunch", "Oats", 80), "diary.food_needed"),
        (("brunch", "Oats, made-up", 80), "diary.meal_needed"),
        (("lunch", "Oats, made-up", 0), "diary.grams_range"),
        (("lunch", "Oats, made-up", config.FOOD_MAX_GRAMS + 1), "diary.grams_range"),
    ],
)
def test_a_bad_row_names_its_problem(row, code):
    """Each field is checked as the food log checks it."""
    with pytest.raises(diary.DiaryError) as caught:
        meal_plans.build_items([row], TABLE)
    assert caught.value.code == code


def test_a_food_twice_in_one_meal_is_refused_but_allowed_in_two():
    """A food once per meal slot; the same food may be in two slots."""
    with pytest.raises(diary.DiaryError) as caught:
        meal_plans.build_items(
            [("lunch", "Oats, made-up", 80), ("lunch", "Oats, made-up", 40)], TABLE
        )
    assert caught.value.code == "meal_plan.twice"
    items = meal_plans.build_items(
        [("lunch", "Oats, made-up", 80), ("dinner", "Oats, made-up", 40)], TABLE
    )
    assert [item.meal for item in items] == ["lunch", "dinner"]


def test_a_coach_saves_a_plan_from_rows_and_the_gymer_reads_it(store_conn, relationships):
    """The rows are looked up in the table, stored with their nutrients and read back."""
    plan_id = meal_plans.save_meal_plan(store_conn, world.COACH_A, world.SHARED, DAY, TABLE)
    plan = store_plans.current_meal_plan(store_conn, world.SHARED, world.SHARED)
    assert plan["id"] == plan_id
    assert [(i["food_name"], i["grams"], i["kcal"]) for i in plan["items"]] == [
        ("Oats, made-up", 200.0, 760.0),
        ("Rice, made-up", 400.0, 520.0),
    ]


def test_a_plan_below_the_floor_gives_its_message_and_writes_nothing(store_conn, relationships):
    """A day under CALORIE_FLOOR_KCAL is the fixed code meal_plan.below_floor; no row."""
    with pytest.raises(diary.DiaryError) as caught:
        meal_plans.save_meal_plan(
            store_conn, world.COACH_A, world.SHARED, [("lunch", "Rice, made-up", 900)], TABLE
        )  # 1170 kcal
    assert caught.value.code == "meal_plan.below_floor"
    assert store_conn.execute("SELECT count(*) FROM meal_plans").fetchone()[0] == 0


def test_an_empty_plan_is_saved_only_by_the_remove_button(store_conn, relationships):
    """save_meal_plan() refuses no rows; remove_meal_plan() saves an empty plan, which hides it."""
    with pytest.raises(diary.DiaryError) as caught:
        meal_plans.save_meal_plan(store_conn, world.COACH_A, world.SHARED, [], TABLE)
    assert caught.value.code == "meal_plan.empty"
    meal_plans.save_meal_plan(store_conn, world.COACH_A, world.SHARED, DAY, TABLE)
    meal_plans.remove_meal_plan(store_conn, world.COACH_A, world.SHARED)
    plan = store_plans.current_meal_plan(store_conn, world.SHARED, world.SHARED)
    assert plan["items"] == []


@pytest.mark.parametrize("client", [world.UNSHARED, world.OTHERS, world.ENDED])
def test_a_coach_s_save_or_remove_outside_a_nutrition_share_is_not_found(
    store_conn, relationships, client
):
    """The store's refusal comes through unchanged: one NotFound for every case."""
    with pytest.raises(access.NotFound):
        meal_plans.save_meal_plan(store_conn, world.COACH_A, client, DAY, TABLE)
    with pytest.raises(access.NotFound):
        meal_plans.remove_meal_plan(store_conn, world.COACH_A, client)


def test_the_totals_per_meal_and_for_the_day():
    """Each slot with foods gets its total, in the food log's order, and the day the sum."""
    items = [
        {"meal": "dinner", "kcal": 500.0, "protein_g": 30.0, "carbohydrate_g": 50.0, "fat_g": 10.0},
        {
            "meal": "breakfast",
            "kcal": 300.0,
            "protein_g": 10.0,
            "carbohydrate_g": 40.0,
            "fat_g": 5.0,
        },
        {"meal": "dinner", "kcal": 200.0, "protein_g": 5.0, "carbohydrate_g": 20.0, "fat_g": 2.0},
    ]
    by_meal = meal_plans.meal_totals(items)
    assert list(by_meal) == ["breakfast", "dinner"]
    assert by_meal["dinner"] == {
        "kcal": 700.0,
        "protein_g": 35.0,
        "carbohydrate_g": 70.0,
        "fat_g": 12.0,
    }
    assert meal_plans.totals(items)["kcal"] == 1000.0
    assert meal_plans.below_floor(items)
    assert not meal_plans.below_floor([])
    assert not meal_plans.below_floor([{**items[0], "kcal": config.CALORIE_FLOOR_KCAL}])
