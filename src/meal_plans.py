"""The coach's meal plan for a client (T11.7): the coach's rows, their nutrients, the day's totals.

The store keeps the plan and decides who may write and read it (`src/store/meal_plans.py`); this
module turns the coach's rows (meal slot, a USDA food name, grams) into the store's items with the
nutrients of their grams from the USDA table, and works out the totals per meal slot and for the
day that the pages show. Foods are the USDA table's own names (T4.8), looked up exactly, never
matched, as the diary does.

A plan is one template day for every day, so its day's energy is a day's intake and is never below
`config.CALORIE_FLOOR_KCAL` (the store refuses it, `BelowCalorieFloor`); an empty plan removes it.
The gymer only reads the plan (nothing is logged from it), and nothing here reaches a model. Not
the chat's `evaluate_meal_plan` tool (T4.5, `src/tools/meal_plan.py`), which checks a plan typed
into the chat and stores nothing.

Each error is a `diary.DiaryError` whose code is the i18n key of its message, which never repeats
what was typed or stored.
"""

import sqlite3
from collections.abc import Iterable, Sequence

from src import config, diary
from src.store import meal_plans
from src.tools.food import Food

NUTRIENTS = meal_plans.NUTRIENTS


def planned_food(
    meal: object, name: object, grams: object, table: Sequence[Food] | None = None
) -> meal_plans.PlannedFood:
    """Return one coach's row as the store's planned food, with the nutrients of its grams."""
    food = diary.find_food(name, table)
    checked_grams = diary.check_grams(grams)
    nutrients = diary.snapshot(food, checked_grams)
    return meal_plans.PlannedFood(
        meal=diary.check_meal(meal),
        fdc_id=food.fdc_id,
        food_name=food.description,
        grams=checked_grams,
        **{key: nutrients[key] for key in NUTRIENTS},
    )


def build_items(
    rows: Iterable[tuple[object, object, object]], table: Sequence[Food] | None = None
) -> list[meal_plans.PlannedFood]:
    """Return the coach's rows (meal slot, food name, grams) as the store's planned foods."""
    items = [planned_food(meal, name, grams, table) for meal, name, grams in rows]
    keys = [(item.meal, item.fdc_id) for item in items]
    if len(set(keys)) != len(keys):
        raise diary.DiaryError("meal_plan.twice")
    return items


def save_meal_plan(
    conn: sqlite3.Connection,
    coach_id: str,
    client_id: str,
    rows: Iterable[tuple[object, object, object]],
    table: Sequence[Food] | None = None,
) -> int:
    """Save the coach's rows as the client's new plan (the store checks access); return its ID."""
    items = build_items(rows, table)
    if not items:
        # An empty plan removes the plan: only remove_meal_plan() saves one, on its own button.
        raise diary.DiaryError("meal_plan.empty")
    try:
        return meal_plans.add_client_meal_plan(conn, coach_id, client_id, items)
    except meal_plans.BelowCalorieFloor:
        raise diary.DiaryError("meal_plan.below_floor") from None


def remove_meal_plan(conn: sqlite3.Connection, coach_id: str, client_id: str) -> int | None:
    """Save an empty plan, which removes the client's plan; None if there is none to remove."""
    # The coach's read (audited, and NotFound wherever the write would be) comes first, so a plan
    # already removed (in another tab, say) is not removed again with a second notification.
    current = meal_plans.current_meal_plan(conn, coach_id, client_id)
    if current is None or not current["items"]:
        return None
    return meal_plans.add_client_meal_plan(conn, coach_id, client_id, [])


def totals(items: Sequence[dict]) -> dict[str, float]:
    """Return the items' total nutrients."""
    return {key: sum(item[key] for item in items) for key in NUTRIENTS}


def meal_totals(items: Sequence[dict]) -> dict[str, dict[str, float]]:
    """Return the total nutrients of each meal slot that has foods, in the food log's order."""
    return {
        meal: totals([item for item in items if item["meal"] == meal])
        for meal in meal_plans.MEALS
        if any(item["meal"] == meal for item in items)
    }


def below_floor(items: Sequence[dict]) -> bool:
    """Return True if a plan with foods has a day's energy below the calorie floor."""
    return bool(items) and totals(items)["kcal"] < config.CALORIE_FLOOR_KCAL
