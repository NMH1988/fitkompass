"""UI tests for the coach's meal plan (T11.7): the coach's form on Client week, the gymer's page.

The coach builds a plan on Client week only while the client shares nutrition: its totals per meal
slot and for the day show next to the client's target, a day below the calorie floor is refused,
and "Remove the plan" saves an empty one. The gymer reads their current coach's plan, read-only,
on the Meal plan page, which says it is the coach's plan, that the app checks neither allergens
nor the coach's qualifications, and credits the USDA data; it is hidden once the relationship ends.
"""

import pytest
from streamlit.testing.v1 import AppTest

from src import config, meal_plans
from src.store import db, users
from src.store import meal_plans as store_plans
from src.store.access import NotFound
from tests.test_app_account import PROFILE, USER_ID, button, signed_in, start, store_account
from tests.test_app_dashboards import (  # noqa: F401 (fixtures used by name)
    ALEX,
    BO,
    _client_week,
    coach_world,
    today,
)
from tests.test_app_sharing import open_page
from tests.test_app_today import POLLOCK
from views import client_week, meal_plan, navigation

pytestmark = pytest.mark.usefixtures("no_env_key")

COACH = "coach-kai-t117"
PECANS = "Nuts, pecans, halves, raw"  # a row of the committed USDA table, about 700 kcal per 100 g


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


def _save(conn, coach: str, client: str, *rows: tuple[str, str, float]) -> int:
    """Save a plan of (meal, food name, grams) for the client as the coach; return its ID."""
    return meal_plans.save_meal_plan(conn, coach, client, rows)


def _plan(user_id: str) -> dict | None:
    """Return a user's active plan, read as the user."""
    with db.connect() as conn:
        return store_plans.current_meal_plan(conn, user_id, user_id)


def _actions() -> list[str]:
    """Return every audit row's action."""
    with db.connect() as conn:
        return [row[0] for row in conn.execute("SELECT action FROM audit_log")]


@pytest.fixture
def coached():
    """Store the canary gymer with a coach sharing nutrition and a saved plan; return the link."""
    store_account("gymer", profile=PROFILE)
    with db.connect() as conn:
        users.create_user(conn, COACH, "coach", "Coach Kai")
        relationship = users.start_relationship(conn, COACH, USER_ID)
        users.set_consent(conn, USER_ID, relationship, "nutrition", True)
        _save(conn, COACH, USER_ID, ("breakfast", PECANS, 150.0), ("dinner", POLLOCK, 250.0))
    return relationship


def _meal_plan_page(monkeypatch, language: str = "en") -> AppTest:
    """Open the gymer's Meal plan page."""
    return open_page(start(monkeypatch, user=signed_in(), language=language), navigation.MEAL_PLAN)


# --- The gymer's Meal plan page ------------------------------------------------------------------


def test_the_gymer_reads_the_coach_s_plan_with_its_notes(monkeypatch, coached):
    """Foods by meal, totals, the coach's name, the not-checked note and the USDA credit."""
    at = _meal_plan_page(monkeypatch)
    text = _page_text(at)
    assert "Meal plan" in text
    assert "The meal plan Coach Kai set for you: one day of meals, the same for every day." in text
    assert f"{PECANS}, 150 g" in text and f"{POLLOCK}, 250 g" in text
    assert "Breakfast total:" in text and "Day total:" in text
    assert "This is your coach's plan, not the app's." in text
    assert "does not check it for allergens or intolerances" in text
    assert "does not check a coach's qualifications" in text
    assert "USDA" in text
    assert "Saved " in text


def test_the_gymer_s_page_has_no_control_that_logs_or_changes_the_plan(monkeypatch, coached):
    """Read-only: no button, input or form on the page beyond the app's own (criterion 3)."""
    at = _meal_plan_page(monkeypatch)
    labels = {str(item.label) for item in at.button}
    assert not {"Log", "Save the plan", "Remove the plan", "Add to the plan"} & labels
    assert not at.number_input and not at.selectbox


def test_the_gymer_s_page_in_german(monkeypatch, coached):
    """The page's heading and notes are German when German is chosen."""
    text = _page_text(_meal_plan_page(monkeypatch, "de"))
    assert "Ernährungsplan" in text
    assert "Das ist der Plan Ihres Coachs, nicht der App." in text
    assert "Tagessumme:" in text


def test_the_plan_is_hidden_once_the_relationship_ends(monkeypatch, coached):
    """A former coach's plan is not shown; the page says a plan comes from a current coach."""
    with db.connect() as conn:
        users.end_relationship(conn, USER_ID, coached)
    text = _page_text(_meal_plan_page(monkeypatch))
    assert PECANS not in text
    assert "You have no meal plan. A meal plan comes from the coach you are connected with." in text
    with db.connect() as conn:  # kept until either side deletes their data
        assert conn.execute("SELECT count(*) FROM meal_plans").fetchone()[0] == 1


def test_a_removed_plan_shows_none(monkeypatch, coached):
    """After the coach removes the plan the gymer is told there is none."""
    with db.connect() as conn:
        meal_plans.remove_meal_plan(conn, COACH, USER_ID)
    text = _page_text(_meal_plan_page(monkeypatch))
    assert "Your coach has not set a meal plan for you." in text and PECANS not in text


def test_a_gymer_without_a_coach_has_no_plan(monkeypatch):
    """No relationship: the page says where a plan comes from."""
    store_account("gymer", profile=PROFILE)
    text = _page_text(_meal_plan_page(monkeypatch))
    assert "A meal plan comes from the coach you are connected with." in text


def test_the_gymer_is_told_of_a_new_plan_on_the_notifications_page(monkeypatch, coached):
    """The notification names the coach, never a food or an amount (criterion 5)."""
    at = open_page(start(monkeypatch, user=signed_in()), navigation.NOTIFICATIONS)
    text = _page_text(at)
    assert "Coach Kai updated your meal plan." in text
    assert PECANS not in text and "150 g" not in text


# --- The coach's form on Client week -------------------------------------------------------------


def _add_row(at: AppTest, food: str, grams: float, meal: str) -> AppTest:
    """Fill the coach's meal plan form and press Add to the plan."""
    at.selectbox(key="meal_plan_food").set_value(food)
    at.number_input(key="meal_plan_grams").set_value(grams)
    at.segmented_control(key="meal_plan_meal").set_value(meal)
    return button(at, "Add to the plan").click().run(timeout=30)


@pytest.mark.usefixtures("coach_world")
def test_a_coach_builds_and_saves_a_plan(monkeypatch):
    """Rows are added, totals show next to the target, Save writes one plan and one audit row."""
    at = _client_week(monkeypatch, chosen=ALEX)
    text = _page_text(at)
    assert "No foods in the plan." in text
    assert "A plan's day total is never below 1,200 kcal, the app's calorie floor." in text
    assert "The app does not check allergens or intolerances" in text
    at = _add_row(at, PECANS, 200.0, "breakfast")
    at = _add_row(at, POLLOCK, 300.0, "dinner")
    text = _page_text(at)
    assert f"{PECANS}, 200 g" in text and "Breakfast total:" in text
    assert "Day total:" in text and "The client's targets today:" in text
    at = button(at, "Save the plan").click().run(timeout=30)
    assert "The meal plan was saved; the client sees it on their Meal plan page." in _page_text(at)
    saved = _plan(ALEX)
    assert [(i["meal"], i["food_name"], i["grams"]) for i in saved["items"]] == [
        ("breakfast", PECANS, 200.0),
        ("dinner", POLLOCK, 300.0),
    ]
    assert saved["coach_id"] == USER_ID
    assert _actions().count("meal_plan_set") == 1


@pytest.mark.usefixtures("coach_world")
def test_a_day_below_the_floor_is_flagged_and_refused(monkeypatch):
    """The draft warns, and Save writes nothing and says why (criterion 2)."""
    at = _client_week(monkeypatch, chosen=ALEX)
    at = _add_row(at, POLLOCK, 500.0, "lunch")  # about 390 kcal
    assert "so the plan cannot be saved like this" in _page_text(at)
    at = button(at, "Save the plan").click().run(timeout=30)
    assert "its day total is below 1,200 kcal, the app's calorie floor" in _page_text(at)
    assert _plan(ALEX) is None and "meal_plan_set" not in _actions()


@pytest.mark.usefixtures("coach_world")
def test_the_draft_starts_from_the_saved_plan_and_the_plan_can_be_removed(monkeypatch):
    """The saved plan fills the draft; a row can be taken out; Remove the plan empties it."""
    with db.connect() as conn:
        _save(conn, USER_ID, ALEX, ("lunch", PECANS, 200.0), ("dinner", POLLOCK, 100.0))
    at = _client_week(monkeypatch, chosen=ALEX)
    assert f"{PECANS}, 200 g" in _page_text(at)
    at.selectbox(key="meal_plan_remove_pick").set_value(1)
    at = button(at, "Remove from the plan").click().run(timeout=30)
    assert f"{POLLOCK}, 100 g" not in _page_text(at)
    at = button(at, "Remove the plan").click().run(timeout=30)
    assert "The meal plan was removed; the client no longer sees one." in _page_text(at)
    assert _plan(ALEX)["items"] == []
    assert not [item for item in at.button if item.label == "Remove the plan"]


@pytest.mark.usefixtures("coach_world")
def test_save_ignores_the_nutrients_kept_in_the_session_draft(monkeypatch):
    """A draft row whose kcal claims the floor is met is looked up again and refused."""
    at = _client_week(monkeypatch, chosen=ALEX)
    row = {
        "meal": "lunch",
        "fdc_id": 1,
        "food_name": POLLOCK,
        "grams": 50.0,  # about 40 kcal in the USDA table
        "kcal": config.CALORIE_FLOOR_KCAL + 300.0,
        "protein_g": 10.0,
        "carbohydrate_g": 0.0,
        "fat_g": 1.0,
    }
    at.session_state[meal_plan.DRAFT_KEY] = {"for": ALEX, "rows": [row], "saved": False}
    at = at.run(timeout=30)
    at = button(at, "Save the plan").click().run(timeout=30)
    assert "its day total is below 1,200 kcal, the app's calorie floor" in _page_text(at)
    assert _plan(ALEX) is None and "meal_plan_set" not in _actions()


@pytest.mark.usefixtures("coach_world")
def test_a_food_twice_in_one_meal_is_refused_in_the_draft(monkeypatch):
    """The second identical row is not added and the page says why."""
    at = _client_week(monkeypatch, chosen=ALEX)
    at = _add_row(at, PECANS, 150.0, "dinner")
    at = _add_row(at, PECANS, 80.0, "dinner")
    assert "A food is in one meal twice; remove one of them." in _page_text(at)
    assert _page_text(at).count(f"{PECANS}, ") == 1


@pytest.mark.usefixtures("coach_world")
def test_no_form_without_nutrition(monkeypatch):
    """Bo shares training only: the section says why and offers no form (criterion 1)."""
    at = _client_week(monkeypatch, chosen=BO)
    assert "A meal plan can be set only while the client shares nutrition." in _page_text(at)
    assert not [item for item in at.button if item.label == "Save the plan"]


@pytest.mark.usefixtures("coach_world")
def test_a_save_refused_after_the_page_was_drawn_shows_one_message(monkeypatch):
    """A share revoked between the page's read and the store's write: one fixed message."""
    at = _client_week(monkeypatch, chosen=ALEX)
    at = _add_row(at, PECANS, 200.0, "dinner")

    def refused(*_args, **_kwargs):
        """Stand in for the store's refusal of a write after the page read the week."""
        raise NotFound

    monkeypatch.setattr(meal_plans, "save_meal_plan", refused)
    at = button(at, "Save the plan").click().run(timeout=30)
    text = _page_text(at)
    assert "The plan was not saved: you cannot set a meal plan for this client now." in text
    assert _plan(ALEX) is None


@pytest.mark.usefixtures("coach_world")
def test_the_coach_s_section_in_german(monkeypatch):
    """The coach's heading and note are German, the floor written the German way."""
    at = open_page(start(monkeypatch, user=signed_in(), language="de"), navigation.CLIENT_WEEK)
    at.selectbox(key=client_week.PICK_KEY).set_value(ALEX).run(timeout=30)
    text = _page_text(at)
    assert "Ernährungsplan" in text
    assert "liegt nie unter 1.200 kcal, der Kaloriengrenze der App" in text
