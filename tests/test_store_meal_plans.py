"""The coach's meal plan for a client (T11.7): who writes and reads it, its limits and the floor."""

from typing import get_args

import pytest

from src import config
from src.store import access, meal_plans, records, users, values
from tests import store_world as world


def _food(meal="lunch", fdc_id=9001, name="Oats, rolled", grams=300.0, kcal=1300.0):
    """Return a planned food with made-up nutrients (the store keeps what the caller worked out)."""
    return meal_plans.PlannedFood(meal, fdc_id, name, grams, kcal, 40.0, 220.0, 20.0)


OATS = _food("breakfast", 9001, "Oats, rolled", 200.0, 760.0)
RICE = _food("lunch", 9002, "Rice, white, cooked", 400.0, 520.0)
DAY = [OATS, RICE]  # 1280 kcal: above the floor


@pytest.fixture
def relationships(store_conn):
    """Build the made-up world in the test's store and return its relationship IDs."""
    return world.build(store_conn)


def _audit(conn):
    """Return every audit row as a dict."""
    return [dict(row) for row in conn.execute("SELECT * FROM audit_log ORDER BY id")]


def _count(conn, table):
    """Return the number of rows in one of the plan's tables."""
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_the_meal_slots_are_the_food_log_s():
    """A plan's meal slots are meal_items' (records.Meal), so no free text names a slot."""
    assert meal_plans.MEALS == get_args(records.Meal)


def test_a_coach_saves_a_plan_and_both_sides_read_it(store_conn, relationships):
    """The plan's items come back in order, with their nutrients, and one audit row each way."""
    plan_id = meal_plans.add_client_meal_plan(store_conn, world.COACH_A, world.SHARED, DAY)
    [written] = _audit(store_conn)
    assert written["action"] == "meal_plan_set"
    assert written["resource_type"] == "meal_plans"
    assert (written["actor_id"], written["subject_id"]) == (world.COACH_A, world.SHARED)
    assert written["resource_id"] == plan_id
    own = meal_plans.current_meal_plan(store_conn, world.SHARED, world.SHARED)
    assert own["id"] == plan_id and own["coach_id"] == world.COACH_A
    assert [
        (i["meal"], i["fdc_id"], i["food_name"], i["grams"], i["kcal"]) for i in own["items"]
    ] == [
        ("breakfast", 9001, "Oats, rolled", 200.0, 760.0),
        ("lunch", 9002, "Rice, white, cooked", 400.0, 520.0),
    ]
    assert {key: own["items"][0][key] for key in meal_plans.NUTRIENTS[1:]} == {
        "protein_g": 40.0,
        "carbohydrate_g": 220.0,
        "fat_g": 20.0,
    }
    assert len(_audit(store_conn)) == 1  # the gymer's own read is not audited
    by_coach = meal_plans.current_meal_plan(store_conn, world.COACH_A, world.SHARED)
    assert by_coach == own
    read = _audit(store_conn)[-1]
    assert (read["action"], read["resource_type"]) == ("read", "meal_plans")
    assert read["resource_id"] is None


def test_the_audit_row_holds_no_value_of_the_plan(store_conn, relationships):
    """The write's audit row has IDs, names and a time only: no food, gram or energy."""
    meal_plans.add_client_meal_plan(store_conn, world.COACH_A, world.SHARED, DAY)
    [row] = _audit(store_conn)
    shown = str(row)
    assert "Oats" not in shown and "760" not in shown and "200.0" not in shown


@pytest.mark.parametrize(
    "total", [config.CALORIE_FLOOR_KCAL - 0.1, 0.0, config.CALORIE_FLOOR_KCAL / 2]
)
def test_a_plan_below_the_calorie_floor_is_refused_and_writes_nothing(
    store_conn, relationships, total
):
    """A day's total under CALORIE_FLOOR_KCAL is refused in code, never naming the total."""
    items = [
        _food("lunch", 1, "Oats", 300.0, total / 2),
        _food("dinner", 2, "Rice", 300.0, total / 2),
    ]
    with pytest.raises(meal_plans.BelowCalorieFloor) as caught:
        meal_plans.add_client_meal_plan(store_conn, world.COACH_A, world.SHARED, items)
    assert isinstance(caught.value, values.StoreValueError) and caught.value.field == "kcal"
    assert str(round(total)) not in str(caught.value)
    assert _count(store_conn, "meal_plans") == 0 and _audit(store_conn) == []


def test_a_plan_at_the_calorie_floor_is_saved(store_conn, relationships):
    """A day's total of exactly CALORIE_FLOOR_KCAL is allowed (the floor is inclusive)."""
    half = config.CALORIE_FLOOR_KCAL / 2
    items = [_food("lunch", 1, "Oats", 300.0, half), _food("dinner", 2, "Rice", 300.0, half)]
    meal_plans.add_client_meal_plan(store_conn, world.COACH_A, world.SHARED, items)
    assert _count(store_conn, "meal_plan_items") == 2


def test_the_newest_plan_is_the_active_one_and_an_empty_plan_removes_it(store_conn, relationships):
    """A coach changes the plan by saving a new one; an empty plan passes and shows no foods."""
    first = meal_plans.add_client_meal_plan(store_conn, world.COACH_A, world.SHARED, DAY)
    second = meal_plans.add_client_meal_plan(
        store_conn, world.COACH_A, world.SHARED, [_food("dinner", 7, "Pasta", 500.0, 1800.0)]
    )
    active = meal_plans.current_meal_plan(store_conn, world.SHARED, world.SHARED)
    assert active["id"] == second and [i["fdc_id"] for i in active["items"]] == [7]
    removed = meal_plans.add_client_meal_plan(store_conn, world.COACH_A, world.SHARED, [])
    active = meal_plans.current_meal_plan(store_conn, world.SHARED, world.SHARED)
    assert active["id"] == removed and active["items"] == []
    assert _count(store_conn, "meal_plans") == 3 and first < second < removed
    assert [row["action"] for row in _audit(store_conn)] == ["meal_plan_set"] * 3


def test_a_user_with_no_plan_reads_none(store_conn, relationships):
    """No plan yet: None for the gymer and for their coach."""
    assert meal_plans.current_meal_plan(store_conn, world.SHARED, world.SHARED) is None
    assert meal_plans.current_meal_plan(store_conn, world.COACH_A, world.SHARED) is None


def test_a_former_coach_s_plan_is_hidden_from_the_gymer_but_kept(store_conn, relationships):
    """Once the relationship ends, the gymer's active plan is None; the rows stay (owner, T11.7)."""
    meal_plans.add_client_meal_plan(store_conn, world.COACH_A, world.SHARED, DAY)
    users.end_relationship(store_conn, world.SHARED, relationships[world.SHARED])
    assert meal_plans.current_meal_plan(store_conn, world.SHARED, world.SHARED) is None
    with pytest.raises(access.NotFound):
        meal_plans.current_meal_plan(store_conn, world.COACH_A, world.SHARED)
    assert _count(store_conn, "meal_plan_items") == 2


def test_a_new_coach_does_not_see_or_show_the_former_coach_s_plan(store_conn, relationships):
    """With a new coach, the gymer sees only the new coach's plan, and that coach only their own."""
    meal_plans.add_client_meal_plan(store_conn, world.COACH_A, world.SHARED, DAY)
    users.end_relationship(store_conn, world.SHARED, relationships[world.SHARED])
    again = users.start_relationship(store_conn, world.COACH_B, world.SHARED)
    users.set_consent(store_conn, world.SHARED, again, "nutrition", True)
    assert meal_plans.current_meal_plan(store_conn, world.SHARED, world.SHARED) is None
    assert meal_plans.current_meal_plan(store_conn, world.COACH_B, world.SHARED) is None
    plan_id = meal_plans.add_client_meal_plan(store_conn, world.COACH_B, world.SHARED, DAY)
    assert meal_plans.current_meal_plan(store_conn, world.SHARED, world.SHARED)["id"] == plan_id


def test_revoking_nutrition_keeps_the_gymer_s_plan_but_stops_the_coach(store_conn, relationships):
    """The gymer still reads the plan while connected; the coach's read and write are refused."""
    meal_plans.add_client_meal_plan(store_conn, world.COACH_A, world.SHARED, DAY)
    users.set_consent(store_conn, world.SHARED, relationships[world.SHARED], "nutrition", False)
    assert meal_plans.current_meal_plan(store_conn, world.SHARED, world.SHARED) is not None
    with pytest.raises(access.NotFound):
        meal_plans.current_meal_plan(store_conn, world.COACH_A, world.SHARED)
    with pytest.raises(access.NotFound):
        meal_plans.add_client_meal_plan(store_conn, world.COACH_A, world.SHARED, DAY)


@pytest.mark.parametrize(
    ("items", "field"),
    [
        ([_food("brunch"), RICE], "meal"),
        ([_food(fdc_id=0), RICE], "fdc_id"),
        ([_food(name=" "), RICE], "food_name"),
        ([_food(grams=0.0), RICE], "grams"),
        ([_food(grams=config.FOOD_MAX_GRAMS + 1), RICE], "grams"),
        ([_food(grams=float("nan")), RICE], "grams"),
        ([_food(kcal=-1.0), RICE], "kcal"),
        ([_food(kcal=float("inf")), RICE], "kcal"),
        ([meal_plans.PlannedFood("lunch", 1, "Oats", 300.0, 1300.0, -1.0, 1.0, 1.0)], "protein_g"),
        (
            [meal_plans.PlannedFood("lunch", 1, "Oats", 300.0, 1300.0, 1.0, True, 1.0)],
            "carbohydrate_g",
        ),
        ([meal_plans.PlannedFood("lunch", 1, "Oats", 300.0, 1300.0, 1.0, 1.0, "9")], "fat_g"),
        ([RICE, RICE], "items"),
        ([("lunch", 1, "Oats", 300.0, 1300.0, 1.0, 1.0, 1.0)], "items"),
        ("oats", "items"),
        (
            [
                _food("snack", n, "Food", 10.0, 100.0)
                for n in range(1, config.MAX_MEAL_PLAN_FOODS + 2)
            ],
            "items",
        ),
    ],
)
def test_a_bad_plan_is_refused_naming_the_field_and_writes_nothing(
    store_conn, relationships, items, field
):
    """A value out of range names its field, never the value; no row and no audit row."""
    with pytest.raises(values.StoreValueError) as caught:
        meal_plans.add_client_meal_plan(store_conn, world.COACH_A, world.SHARED, items)
    assert caught.value.field == field
    assert "Oats" not in str(caught.value) and "300" not in str(caught.value)
    assert _count(store_conn, "meal_plans") == 0 and _audit(store_conn) == []


def test_the_longest_plan_and_one_food_in_two_meals_are_allowed(store_conn, relationships):
    """MAX_MEAL_PLAN_FOODS items fit, and a food may be planned for two meal slots."""
    longest = [
        _food("snack", n, "Food", 10.0, 100.0) for n in range(1, config.MAX_MEAL_PLAN_FOODS + 1)
    ]
    meal_plans.add_client_meal_plan(store_conn, world.COACH_A, world.SHARED, longest)
    twice = [OATS, _food("snack", OATS.fdc_id, OATS.food_name, 200.0, 760.0)]
    meal_plans.add_client_meal_plan(store_conn, world.COACH_A, world.SHARED, twice)
    assert _count(store_conn, "meal_plans") == 2


def test_a_gymer_has_no_way_to_delete_or_change_a_plan(store_conn, relationships):
    """delete_record() has no kind for plans, and a stored plan row is never changed in place."""
    meal_plans.add_client_meal_plan(store_conn, world.COACH_A, world.SHARED, DAY)
    assert not any("plan" in kind for kind in records.RECORD_KINDS)
    with pytest.raises(values.StoreValueError):
        records.delete_record(store_conn, world.SHARED, "meal_plans", 1)
    with pytest.raises(Exception, match="never changed in place"):
        store_conn.execute("UPDATE meal_plan_items SET grams = 1")
