"""UI tests for the coach's Recipe library and the gymer's Recipes page (T11.8, AC-48).

The coach writes, edits and deletes recipes and sees a recipe's average only from the minimum number
of raters who share nutrition, never who rated. The gymer reads their current coach's recipes, once
they have saved a profile, with the not-checked note and the USDA credit; logs one at a portion they
choose, each food marked as from the recipe; and rates a recipe they logged, told what the coach
sees of it. The coach's steps show with images and links as plain text. English and German.
"""

import pytest
from streamlit.testing.v1 import AppTest

from src import config, metrics
from src import recipes as recipe_service
from src.store import db, ratings, records, users
from src.store import recipes as store_recipes
from tests.test_app_account import PROFILE, USER_ID, button, signed_in, start, store_account
from tests.test_app_meal_plan import PECANS
from tests.test_app_sharing import open_page
from tests.test_app_today import POLLOCK
from views import navigation

pytestmark = pytest.mark.usefixtures("no_env_key")

COACH = "coach-kai-t118"
NAME = "Pecan pollock bake"
# Markdown with an image and a link: the image must not load and the link must not be one.
STEPS = (
    "**Heat** the oven. ![tracker](https://example.invalid/pixel.png) "
    "See [my site](https://example.invalid/page) or https://example.invalid/bare."
)


def _page_text(at: AppTest) -> str:
    """Return every caption, Markdown, message and subheader of the page as one text."""
    parts = [
        *at.caption,
        *at.markdown,
        *at.error,
        *at.subheader,
        *at.info,
        *at.success,
        *at.warning,
    ]
    return "\n".join(str(part.value) for part in parts)


def _recipe(conn, coach: str = COACH, name: str = NAME) -> int:
    """Save the coach's two-food recipe; return its ID."""
    return recipe_service.save_recipe(
        conn, coach, None, name=name, steps=STEPS, rows=[(PECANS, 50.0), (POLLOCK, 200.0)]
    )


def _gymer_items() -> list[dict]:
    """Return the canary gymer's meal items, read as the gymer."""
    with db.connect() as conn:
        return records.list_meal_items(conn, USER_ID, USER_ID)


@pytest.fixture
def coached():
    """Store the canary gymer with a profile, a coach sharing nutrition and a recipe; return it."""
    store_account("gymer", profile=PROFILE)
    with db.connect() as conn:
        users.create_user(conn, COACH, "coach", "Coach Kai")
        relationship = users.start_relationship(conn, COACH, USER_ID)
        users.set_consent(conn, USER_ID, relationship, "nutrition", True)
        return {"relationship": relationship, "recipe": _recipe(conn)}


def _recipes_page(monkeypatch, language: str = "en") -> AppTest:
    """Open the gymer's Recipes page."""
    return open_page(start(monkeypatch, user=signed_in(), language=language), navigation.RECIPES)


# --- The gymer's Recipes page ---------------------------------------------------------------------


def test_the_gymer_reads_the_coach_s_recipe_with_its_notes(monkeypatch, coached):
    """The coach's name, the foods and total, the steps, the not-checked note and USDA's credit."""
    text = _page_text(_recipes_page(monkeypatch))
    assert "Recipes by Coach Kai, shared with all their clients." in text
    assert f"{PECANS}: 50 g" in text and f"{POLLOCK}: 200 g" in text
    assert "Total:" in text
    assert "**Heat** the oven." in text
    assert "These are your coach's recipes, not the app's." in text
    assert "does not check them for allergens or intolerances" in text
    assert "does not check a coach's qualifications" in text
    assert "USDA" in text
    assert "Log this recipe to rate it." in text


def test_the_steps_load_no_image_and_hold_no_link(monkeypatch, coached):
    """The image is its alt text and each link plain, escaped text; the address stays readable."""
    at = _recipes_page(monkeypatch)
    [steps] = [str(m.value) for m in at.markdown if "Heat" in str(m.value)]
    assert "![" not in steps and "](" not in steps
    assert "tracker" in steps and "my site" in steps
    assert "https:" + recipe_service.WORD_JOINER + "//example.invalid/bare" in steps


def test_the_gymer_logs_the_recipe_at_a_portion(monkeypatch, coached):
    """Half a portion: each food at half its grams for the chosen meal, marked from the recipe."""
    at = _recipes_page(monkeypatch)
    at.segmented_control(key="recipes_meal").set_value("lunch")
    at.select_slider(key=f"recipe_portion_{coached['recipe']}").set_value(0.5).run(timeout=30)
    assert f"{PECANS}: 25 g" in _page_text(at)
    at = button(at, "Log this recipe").click().run(timeout=30)
    assert "Recipe logged." in _page_text(at)
    items = _gymer_items()
    assert [(i["food_name"], i["grams"], i["meal"]) for i in items] == [
        (PECANS, 25.0, "lunch"),
        (POLLOCK, 100.0, "lunch"),
    ]
    assert {i["from_recipe"] for i in items} == {coached["recipe"]}


def test_logging_needs_a_meal(monkeypatch, coached):
    """The Log button stays off until a meal is picked."""
    at = _recipes_page(monkeypatch)
    assert button(at, "Log this recipe").disabled
    at.segmented_control(key="recipes_meal").set_value("dinner").run(timeout=30)
    assert not button(at, "Log this recipe").disabled


@pytest.mark.parametrize(
    ("language", "note"),
    [
        ("en", "With few clients your coach may still work out your rating"),
        ("de", "Bei wenigen Klienten kann er Ihre Bewertung trotzdem erschließen"),
    ],
)
def test_a_gymer_who_logged_it_rates_it_and_is_told_what_the_coach_sees(
    monkeypatch, coached, language, note
):
    """Stars appear after a log; a rating is saved; the note on what the coach may work out."""
    with db.connect() as conn:
        recipe_service.log_recipe(
            conn, USER_ID, coached["recipe"], factor=1.0, meal="lunch", day=_today()
        )
    at = _recipes_page(monkeypatch, language)
    assert note in _page_text(at)
    at.feedback(key=f"recipe_rating_{coached['recipe']}").set_value(3).run(timeout=30)
    with db.connect() as conn:
        assert ratings.own_rating(conn, USER_ID, coached["recipe"]) == 4
    # Reloading the page shows the saved rating and saves nothing new.
    at = _recipes_page(monkeypatch, language)
    assert at.feedback(key=f"recipe_rating_{coached['recipe']}").value == 3
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM recipe_ratings").fetchone()[0] == 1


def _today():
    """Return today's Berlin date, the diary's day."""
    return metrics.berlin_day()


def test_the_gymer_s_page_in_german(monkeypatch, coached):
    """The heading, the not-checked note and the total are German when German is chosen."""
    text = _page_text(_recipes_page(monkeypatch, "de"))
    assert "Rezepte" in text
    assert "Das sind die Rezepte Ihres Coachs, nicht der App." in text
    assert "Summe:" in text


def test_the_recipes_are_hidden_once_the_relationship_ends(monkeypatch, coached):
    """A former coach's recipes are not shown; the page says recipes come from a current coach."""
    with db.connect() as conn:
        users.end_relationship(conn, USER_ID, coached["relationship"])
    text = _page_text(_recipes_page(monkeypatch))
    assert NAME not in text
    assert "Recipes come from the coach you are connected with." in text


def test_a_coach_with_no_recipes_says_so(monkeypatch, coached):
    """A current coach who has written none."""
    with db.connect() as conn:
        store_recipes.delete_recipe(conn, COACH, coached["recipe"])
    assert "Your coach has not written any recipes yet." in _page_text(_recipes_page(monkeypatch))


@pytest.mark.parametrize(
    ("language", "notice"),
    [
        ("en", "Save your details on My profile first: the app is for adults"),
        ("de", "Speichern Sie zuerst Ihre Angaben unter Mein Profil: Die App ist für Erwachsene"),
    ],
)
def test_the_recipes_show_only_after_the_gymer_saved_a_profile(monkeypatch, language, notice):
    """No declared age yet (the profile's 18+ check): the page asks for it and hides the recipes."""
    store_account("gymer")
    with db.connect() as conn:
        users.create_user(conn, COACH, "coach", "Coach Kai")
        relationship = users.start_relationship(conn, COACH, USER_ID)
        users.set_consent(conn, USER_ID, relationship, "nutrition", True)
        _recipe(conn)
    text = _page_text(_recipes_page(monkeypatch, language))
    assert notice in text
    assert NAME not in text and "Coach Kai" not in text


# --- The coach's Recipe library -----------------------------------------------------------------


@pytest.fixture
def coach_account():
    """Store the canary user as a coach."""
    store_account("coach", name="Coach Kai")


def _library(monkeypatch, language: str = "en") -> AppTest:
    """Open the coach's Recipe library."""
    at = start(monkeypatch, user=signed_in(), language=language)
    return open_page(at, navigation.RECIPE_LIBRARY)


def _add_food(at: AppTest, food: str, grams: float) -> AppTest:
    """Fill the draft's food form and press Add to the recipe."""
    at.selectbox(key="recipe_food").set_value(food)
    at.number_input(key="recipe_grams").set_value(grams)
    return button(at, "Add to the recipe").click().run(timeout=30)


def _own_recipes() -> list[dict]:
    """Return the canary coach's recipes."""
    with db.connect() as conn:
        return store_recipes.list_recipes(conn, USER_ID)


@pytest.mark.usefixtures("coach_account")
def test_a_coach_writes_and_saves_a_recipe(monkeypatch):
    """Name, steps and two foods; Save stores one recipe with the table's nutrients."""
    at = _library(monkeypatch)
    text = _page_text(at)
    assert "You have no recipes yet." in text
    assert "The app does not check a recipe for allergens or intolerances" in text
    at.text_input(key="recipe_name").set_value(NAME)
    at.text_area(key="recipe_steps").set_value("Bake for 20 minutes.")
    at = _add_food(at, PECANS, 50.0)
    at = _add_food(at, POLLOCK, 200.0)
    assert f"{PECANS}: 50 g" in _page_text(at)
    at = button(at, "Save the recipe").click().run(timeout=30)
    assert "Recipe saved." in _page_text(at)
    [saved] = _own_recipes()
    assert (saved["name"], saved["steps"]) == (NAME, "Bake for 20 minutes.")
    assert [(f["food_name"], f["grams"]) for f in saved["ingredients"]] == [
        (PECANS, 50.0),
        (POLLOCK, 200.0),
    ]
    assert NAME in [str(item.label) for item in at.expander]
    assert "Not enough ratings yet." in _page_text(at)


@pytest.mark.usefixtures("coach_account")
def test_a_recipe_without_a_name_is_refused(monkeypatch):
    """Save with foods but no name: a fixed message, nothing stored."""
    at = _library(monkeypatch)
    at.text_area(key="recipe_steps").set_value("Bake.")
    at = _add_food(at, PECANS, 50.0)
    at = button(at, "Save the recipe").click().run(timeout=30)
    assert "Give the recipe a name." in _page_text(at)
    assert _own_recipes() == []


@pytest.mark.usefixtures("coach_account")
@pytest.mark.parametrize(
    ("language", "warning"),
    [
        ("en", "Every client you are connected with sees every recipe: do not name a client"),
        ("de", "Jeder Klient, mit dem Sie verbunden sind, sieht jedes Rezept: Nennen Sie darin"),
    ],
)
def test_the_coach_is_told_every_client_sees_every_recipe(monkeypatch, language, warning):
    """The intro warns the coach not to name a client or write about anyone's health."""
    assert warning in _page_text(_library(monkeypatch, language))


@pytest.mark.usefixtures("coach_account")
def test_a_food_is_taken_out_and_the_pick_cleared_when_another_recipe_opens(monkeypatch):
    """Take out removes the picked food; Edit on a shorter recipe starts with no pick."""
    with db.connect() as conn:
        _recipe(conn, USER_ID)
        recipe_service.save_recipe(
            conn, USER_ID, None, name="Pecans only", steps="Eat.", rows=[(PECANS, 30.0)]
        )
    at = _library(monkeypatch)
    at = _add_food(at, PECANS, 50.0)
    at = _add_food(at, POLLOCK, 200.0)
    at.selectbox(key="recipe_remove_pick").set_value(1)
    at = button(at, "Take out").click().run(timeout=30)
    assert [row["food_name"] for row in at.session_state["recipe_draft"]["rows"]] == [PECANS]
    at.selectbox(key="recipe_remove_pick").set_value(0)
    edit_buttons = [item for item in at.button if item.label == "Edit"]
    at = edit_buttons[-1].click().run(timeout=30)
    assert at.text_input(key="recipe_name").value == "Pecans only"
    assert at.selectbox(key="recipe_remove_pick").value is None
    assert not at.exception


@pytest.mark.usefixtures("coach_account")
def test_an_edit_keeps_the_recipe_s_id(monkeypatch):
    """Edit opens the draft with the recipe; Save adds a version under the same ID."""
    with db.connect() as conn:
        recipe_id = _recipe(conn, USER_ID)
    at = _library(monkeypatch)
    at = button(at, "Edit").click().run(timeout=30)
    assert at.text_input(key="recipe_name").value == NAME
    at.text_input(key="recipe_name").set_value("Pecan pollock bake, lighter")
    at = button(at, "Save the recipe").click().run(timeout=30)
    [saved] = _own_recipes()
    assert (saved["id"], saved["name"]) == (recipe_id, "Pecan pollock bake, lighter")


@pytest.mark.usefixtures("coach_account")
def test_delete_asks_first_then_removes_the_recipe(monkeypatch):
    """Delete shows the confirmation; Keep it keeps the recipe; Delete for good removes it."""
    with db.connect() as conn:
        _recipe(conn, USER_ID)
    at = _library(monkeypatch)
    at = button(at, "Delete").click().run(timeout=30)
    assert "Delete this recipe with its ratings?" in _page_text(at)
    at = button(at, "Keep it").click().run(timeout=30)
    assert len(_own_recipes()) == 1
    at = button(at, "Delete").click().run(timeout=30)
    at = button(at, "Delete for good").click().run(timeout=30)
    assert "Recipe deleted." in _page_text(at)
    assert _own_recipes() == []


def _rated_by(recipe_id: int, *stars: int, sharing: bool = True) -> None:
    """Make one client of the canary coach per star count, who logged and rated the recipe."""
    with db.connect() as conn:
        for index, count in enumerate(stars):
            client = f"gym-rater-{index}"
            users.create_user(conn, client, "gymer", f"Rater {index}")
            relationship = users.start_relationship(conn, USER_ID, client)
            users.set_consent(conn, client, relationship, "nutrition", sharing)
            records.add_recipe_items(
                conn, client, recipe_id, consumed_on=_today(), meal="lunch", factor=1.0
            )
            ratings.rate_recipe(conn, client, recipe_id, count)


@pytest.mark.usefixtures("coach_account")
def test_the_coach_sees_the_average_from_the_minimum_and_never_who_rated(monkeypatch):
    """Three sharing raters: the average and count; no rater's name anywhere on the page."""
    assert config.RATING_MIN_RATERS == 3
    with db.connect() as conn:
        recipe_id = _recipe(conn, USER_ID)
    _rated_by(recipe_id, 3, 4, 5)
    text = _page_text(_library(monkeypatch))
    assert "Rated 4 of 5 by 3 clients." in text
    assert "Rater" not in text and "gym-rater" not in text


@pytest.mark.usefixtures("coach_account")
def test_below_the_minimum_the_coach_sees_no_average_and_no_count(monkeypatch):
    """Two raters: not enough yet, and no number of raters."""
    with db.connect() as conn:
        recipe_id = _recipe(conn, USER_ID)
    _rated_by(recipe_id, 3, 4)
    text = _page_text(_library(monkeypatch))
    assert "Not enough ratings yet." in text
    assert "Rated" not in text and "by 2 clients" not in text


@pytest.mark.usefixtures("coach_account")
def test_ratings_of_clients_who_do_not_share_nutrition_are_not_counted(monkeypatch):
    """Three raters who share nothing count as none."""
    with db.connect() as conn:
        recipe_id = _recipe(conn, USER_ID)
    _rated_by(recipe_id, 5, 5, 5, sharing=False)
    assert "Not enough ratings yet." in _page_text(_library(monkeypatch))


@pytest.mark.usefixtures("coach_account")
def test_the_coach_s_page_in_german(monkeypatch):
    """The heading and the notes are German when German is chosen."""
    with db.connect() as conn:
        recipe_id = _recipe(conn, USER_ID)
    _rated_by(recipe_id, 4, 4, 5)
    text = _page_text(_library(monkeypatch, "de"))
    assert "Rezeptsammlung" in text
    assert "Die App prüft Rezepte nicht auf Allergene oder Unverträglichkeiten" in text
    assert "Von 3 Klienten mit 4,3 von 5 Sternen bewertet." in text


def test_each_role_has_its_recipe_page_and_not_the_other_s():
    """The coach's library and the gymer's page are each registered for their role only."""
    assert navigation.RECIPE_LIBRARY in navigation.PAGES_BY_ROLE["coach"]
    assert navigation.RECIPES not in navigation.PAGES_BY_ROLE["coach"]
    assert navigation.RECIPES in navigation.PAGES_BY_ROLE["gymer"]
    assert navigation.RECIPE_LIBRARY not in navigation.PAGES_BY_ROLE["gymer"]
