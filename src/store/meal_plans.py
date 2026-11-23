"""The coach's meal plan for a client (T11.7): one template day that applies to every day.

A plan is written only by the client's coach while the client shares nutrition
(`add_client_meal_plan()`): the share check, the inserts and an audit row with no values
(`meal_plan_set`) run in one transaction, and every other case is the same `NotFound`, with no row
and no audit row, as a coach's target (T9.17) and list of suggested foods (T9.34) are. A coach
changes the plan by saving a new one; an empty plan removes it. Items use the food log's meal slots
(no free text, so nothing the coach types reaches a later model call, T11.9) and grams, at most
`config.MAX_MEAL_PLAN_FOODS` of them, a food at most once per meal slot. Each item keeps the
nutrients of its grams, worked out by the caller from the USDA table, and a plan with foods whose
day's energy is below `config.CALORIE_FLOOR_KCAL` is refused (`BelowCalorieFloor`): a plan is a
day's intake, so the floor holds for it as for a target (docs/PRD.md, guardrails).

`current_meal_plan()` reads the active plan. For the gymer it is the newest plan written by the
coach they are connected with now, so a former coach's plan is hidden once the relationship ends,
though kept (in the gymer's export) until either side deletes their data. For a coach it is the
newest plan they wrote for the client, read through `access.authorised_read()` (nutrition, an
audited read). A relationship's status is read as a value (`ended_at`), never as a sharing filter,
which only the `open_shares` view writes. The gymer only reads a plan: nothing is logged from it.
"""

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from src import config
from src.store import values
from src.store.access import NotFound, audit, authorise_read, authorised_read
from src.store.db import transaction

# The meal slots, as meal_items has them (records.Meal); a test checks they are the same.
MEALS: tuple[str, ...] = ("breakfast", "lunch", "dinner", "snack")
# The nutrients each item keeps, as meal_items name them.
NUTRIENTS: tuple[str, ...] = ("kcal", "protein_g", "carbohydrate_g", "fat_g")

_ADD_PLAN = "INSERT INTO meal_plans (client_id, coach_id, created_at) VALUES (?, ?, ?)"
_ADD_ITEM = """
INSERT INTO meal_plan_items
    (plan_id, meal, fdc_id, food_name, grams, kcal, protein_g, carbohydrate_g, fat_g)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
# The client's relationships, their status read as a value (never a sharing filter).
_CLIENT_RELATIONSHIPS = (
    "SELECT coach_id, ended_at FROM coach_clients WHERE client_id = ? ORDER BY id"
)
_NEWEST_PLAN = """
SELECT id, coach_id, created_at FROM meal_plans
WHERE client_id = ? AND coach_id = ? ORDER BY id DESC LIMIT 1
"""
_ITEMS = """
SELECT id, meal, fdc_id, food_name, grams, kcal, protein_g, carbohydrate_g, fat_g
FROM meal_plan_items WHERE plan_id = ? ORDER BY id
"""


class BelowCalorieFloor(values.StoreValueError):
    """Raised for a plan with foods whose day's energy is below the calorie floor."""

    def __init__(self) -> None:
        """Name the field and the fixed problem, never the total."""
        super().__init__("kcal", "is below the calorie floor for the day")


@dataclass(frozen=True)
class PlannedFood:
    """One food of the plan: the meal slot, the USDA food, the grams and their nutrients."""

    meal: str
    fdc_id: int
    food_name: str
    grams: float
    kcal: float
    protein_g: float
    carbohydrate_g: float
    fat_g: float


def _checked_items(items: object) -> list[tuple]:
    """Return the items as checked rows, refusing a bad plan or one below the calorie floor."""
    if isinstance(items, str | bytes) or not isinstance(items, Sequence):
        raise values.StoreValueError("items", "must be a list of planned foods")
    if len(items) > config.MAX_MEAL_PLAN_FOODS:
        raise values.StoreValueError("items", "holds more foods than allowed")
    rows: list[tuple] = []
    seen: set[tuple[str, int]] = set()
    for item in items:
        if not isinstance(item, PlannedFood):
            raise values.StoreValueError("items", "must be a list of planned foods")
        meal = values.choice(item.meal, "meal", MEALS)
        fdc_id = values.whole_number(item.fdc_id, "fdc_id", minimum=1)
        if (meal, fdc_id) in seen:
            raise values.StoreValueError("items", "names a food twice for one meal")
        seen.add((meal, fdc_id))
        rows.append(
            (
                meal,
                fdc_id,
                values.text(item.food_name, "food_name"),
                values.in_range(
                    item.grams, "grams", (config.FOOD_MIN_GRAMS, config.FOOD_MAX_GRAMS)
                ),
                values.number(item.kcal, "kcal"),
                values.number(item.protein_g, "protein_g"),
                values.number(item.carbohydrate_g, "carbohydrate_g"),
                values.number(item.fat_g, "fat_g"),
            )
        )
    # An empty plan removes the plan, so the floor holds only for a plan with foods.
    # Each row is (meal, fdc_id, food_name, grams, kcal, protein_g, carbohydrate_g, fat_g).
    if rows and sum(row[4] for row in rows) < config.CALORIE_FLOOR_KCAL:
        raise BelowCalorieFloor
    return rows


def add_client_meal_plan(
    conn: sqlite3.Connection, coach_id: str, client_id: str, items: Sequence[PlannedFood]
) -> int:
    """Save a coach's new meal plan for a client sharing nutrition; return its ID."""
    # The items are checked before the transaction, so a bad value writes nothing. The share check,
    # the inserts and the audit row are one transaction; anything but a coach of a gymer with an
    # active relationship and nutrition shared (the coach's own ID included, for which
    # authorise_read() returns False) is the same NotFound, with no row and no audit row.
    try:
        values.user_id(client_id)
    except values.StoreValueError:
        raise NotFound from None  # as a read of a subject that is not an ID
    rows = _checked_items(items)
    with transaction(conn):
        if authorise_read(conn, coach_id, client_id, "nutrition") is not True:
            raise NotFound
        plan_id = conn.execute(_ADD_PLAN, (client_id, coach_id, values.utc_text())).lastrowid
        for row in rows:
            conn.execute(_ADD_ITEM, (plan_id, *row))
        # Who wrote what kind of record about whom and when, never a value (PRD, Audit).
        audit(
            conn,
            coach_id,
            "meal_plan_set",
            "meal_plans",
            subject_id=client_id,
            resource_id=plan_id,
        )
        return plan_id


def _current_coach(conn: sqlite3.Connection, client_id: str) -> str | None:
    """Return the coach the client is connected with now, or None."""
    for row in conn.execute(_CLIENT_RELATIONSHIPS, (client_id,)).fetchall():
        if row["ended_at"] is None:
            return row["coach_id"]
    return None


def _plan_with_items(conn: sqlite3.Connection, client_id: str, coach_id: str) -> dict | None:
    """Return the newest plan a coach wrote for a client, with its items, or None."""
    found = conn.execute(_NEWEST_PLAN, (client_id, coach_id)).fetchone()
    if found is None:
        return None
    items = [dict(row) for row in conn.execute(_ITEMS, (found["id"],))]
    return {**dict(found), "items": items}


def current_meal_plan(conn: sqlite3.Connection, actor_id: str, subject_id: str) -> dict | None:
    """Return the active plan (id, coach_id, created_at, items) a user may read, or None."""
    with authorised_read(conn, actor_id, subject_id, "nutrition", "meal_plans"):
        if actor_id != subject_id:
            # A coach, allowed by authorised_read(): the newest plan they wrote for this client.
            return _plan_with_items(conn, subject_id, actor_id)
        # The user's own: the plan of the coach they are connected with now, if any.
        coach_id = _current_coach(conn, subject_id)
        return None if coach_id is None else _plan_with_items(conn, subject_id, coach_id)
