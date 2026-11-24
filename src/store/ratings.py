"""The clients' ratings of their coach's recipes (T11.8): 1 to 5 stars, the newest per client.

A rating is the gymer's data. A gymer rates a recipe only while its coach is the coach they are
connected with now and after they logged its dish (a meal item of theirs marked `from_recipe` with
it); every other case, a recipe that is gone included, is the same `NotFound` with nothing written
(`rate_recipe()`). A new rating is a new row, as the store never changes one in place, and the
newest per client counts. A gymer reads only their own (`own_rating()`).

The coach never sees who rated or a single rating: `rating_summaries()` gives, for each of the
coach's own recipes, the average and the count of the newest ratings of clients who share nutrition
with the coach now (read from the `open_shares` view, so the count cannot tell the coach that a
client who does not share logged the dish), and only once at least `config.RATING_MIN_RATERS` of
them have rated; below that, nothing, not even the count. This read is built from gymers' rows but
holds no single person's value, so it is not audited (T11.8, a recorded exception to auditing
every coach read). With few clients a coach may still work out a rating from
how the average moves, a known limit (`docs/SECURITY.md`).
"""

import sqlite3

from src import config
from src.store import recipes, values
from src.store.access import NotFound, role_of
from src.store.db import transaction

STARS: tuple[int, ...] = (1, 2, 3, 4, 5)

_LOGGED = "SELECT 1 FROM meal_items WHERE user_id = ? AND from_recipe = ? LIMIT 1"
_ADD = "INSERT INTO recipe_ratings (recipe_id, client_id, stars, created_at) VALUES (?, ?, ?, ?)"
_OWN = """
SELECT stars FROM recipe_ratings WHERE recipe_id = ? AND client_id = ? ORDER BY id DESC LIMIT 1
"""
# Per recipe of the coach: the newest rating of each client who shares nutrition with the coach
# now, counted and averaged in SQL, so no client's ID or stars leave the query.
_SUMMARIES = """
SELECT rating.recipe_id AS recipe_id, count(*) AS raters, avg(rating.stars) AS average
FROM recipe_ratings AS rating
JOIN recipes AS recipe ON recipe.id = rating.recipe_id
WHERE recipe.coach_id = ?
    AND rating.id = (
        SELECT max(newer.id) FROM recipe_ratings AS newer
        WHERE newer.recipe_id = rating.recipe_id AND newer.client_id = rating.client_id
    )
    AND EXISTS (
        SELECT 1 FROM open_shares AS share
        WHERE share.coach_id = recipe.coach_id AND share.client_id = rating.client_id
          AND share.scope = 'nutrition'
    )
GROUP BY rating.recipe_id
"""


def _may_rate(conn: sqlite3.Connection, user_id: str, recipe_id: object) -> bool:
    """Return True if the gymer's current coach wrote the recipe and the gymer logged its dish."""
    # Runs inside the caller's transaction.
    if recipes.recipe_for_client(conn, user_id, recipe_id) is None:
        return False
    return conn.execute(_LOGGED, (user_id, recipe_id)).fetchone() is not None


def _checked_user(user_id: object) -> str:
    """Return the user ID, or raise NotFound for a value that is not one."""
    try:
        return values.user_id(user_id)
    except values.StoreValueError:
        raise NotFound from None


def rate_recipe(conn: sqlite3.Connection, user_id: str, recipe_id: int, stars: int) -> int:
    """Save the gymer's rating of a recipe they logged, from their current coach; return its ID."""
    user_id = _checked_user(user_id)
    checked_stars = values.whole_number(stars, "stars", minimum=1, maximum=5)
    with transaction(conn):
        if not _may_rate(conn, user_id, recipe_id):
            raise NotFound
        return conn.execute(_ADD, (recipe_id, user_id, checked_stars, values.utc_text())).lastrowid


def can_rate(conn: sqlite3.Connection, user_id: str, recipe_id: int) -> bool:
    """Return True if the user may rate the recipe now (the check rate_recipe() makes)."""
    user_id = _checked_user(user_id)
    with transaction(conn):
        return _may_rate(conn, user_id, recipe_id)


def own_rating(conn: sqlite3.Connection, user_id: str, recipe_id: int) -> int | None:
    """Return the stars of the user's own newest rating of a recipe, or None."""
    user_id = _checked_user(user_id)
    if not values.is_row_id(recipe_id):
        return None
    with transaction(conn):
        if role_of(conn, user_id) is None:
            raise NotFound
        found = conn.execute(_OWN, (recipe_id, user_id)).fetchone()
    return None if found is None else found["stars"]


def rating_summaries(conn: sqlite3.Connection, coach_id: str) -> dict[int, tuple[float, int]]:
    """Return {recipe ID: (average, raters)} of the coach's recipes rated by enough clients."""
    # A recipe with fewer counted raters than config.RATING_MIN_RATERS is left out, with its count.
    coach_id = _checked_user(coach_id)
    with transaction(conn):
        if role_of(conn, coach_id) != "coach":
            raise NotFound
        rows = conn.execute(_SUMMARIES, (coach_id,)).fetchall()
    return {
        row["recipe_id"]: (row["average"], row["raters"])
        for row in rows
        if row["raters"] >= config.RATING_MIN_RATERS
    }
