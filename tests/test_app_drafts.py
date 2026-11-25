"""UI tests for the AI drafts from a gymer's own messages on the Messages page (T11.5)."""

import json

import pytest
from streamlit.testing.v1 import AppTest

from src import config, diary, drafting, guard, llm, metrics
from src.store import ai_consents, db, messages, users
from src.tools.food import load_food_table
from tests.fakes import ScriptedTranslator
from tests.test_app_account import PROFILE, USER_ID, store_account, texts
from tests.test_app_messages import _pair, _run, _user
from views import resources

pytestmark = pytest.mark.usefixtures("no_env_key")

COACH = "coach-ola"
EGG = "Egg, whole, raw, frozen, pasteurized"


def _reply() -> str:
    """Return a model reply with one food and one weight."""
    return json.dumps(
        {
            "foods": [{"food": EGG, "grams": 100.0, "meal": "breakfast"}],
            "weight": {"value": 74.0, "unit": "kg"},
            "workout": [],
        }
    )


@pytest.fixture
def gymer_thread(monkeypatch, tmp_path):
    """Store the signed-in gymer with a profile, a coach, a thread and one message of theirs."""
    assert any(food.description == EGG for food in load_food_table())
    store_account("gymer", "Mia", profile=PROFILE)
    _user(COACH, "coach", "Coach Ola")
    thread = _pair(COACH, USER_ID)
    with db.connect() as conn:
        messages.send_message(conn, USER_ID, thread, "CANARY-MSG two eggs, 74 kg this morning")
    prompt = tmp_path / "draft_entries_system.md"
    prompt.write_text("Draft the client's log entries. Test prompt.", encoding="utf-8")
    monkeypatch.setattr(config, "DRAFT_PROMPT_PATH", prompt)
    return thread


@pytest.fixture
def fake_model(monkeypatch):
    """Replace the draft model with a scripted fake that records its requests."""
    fake = ScriptedTranslator(plans=[_reply()], model_name=config.DRAFT_MODEL)
    monkeypatch.setattr(resources, "draft_model", lambda: fake)
    return fake


def _consent():
    """Give the signed-in gymer's consent (a) to the current text."""
    with db.connect() as conn:
        ai_consents.give(conn, USER_ID, drafting.PURPOSE, drafting.consent_version())


def _logged(table: str) -> int:
    """Return how many rows of a record table the signed-in gymer has."""
    with db.connect() as conn:
        query = f"SELECT count(*) FROM {table} WHERE user_id = ?"
        return conn.execute(query, (USER_ID,)).fetchone()[0]


def _button(at: AppTest, label: str):
    """Return the one button with this label."""
    [found] = [item for item in at.button if item.label == label]
    return found


def _decide(at: AppTest, *choices: str) -> None:
    """Pick each card's choice, in order (no card has one before the gymer picks it)."""
    actions = [item for item in at.button_group if item.label in ("Decision", "Entscheidung")]
    assert len(actions) == len(choices)
    for action, choice in zip(actions, choices, strict=True):
        action.set_value(choice)


def _success(at: AppTest) -> str:
    """Return the page's success notes as one text."""
    return "\n".join(str(item.value) for item in at.success)


def _labels(at: AppTest) -> list[str]:
    """Return the labels of the page's buttons."""
    return [item.label for item in at.button]


@pytest.mark.parametrize(
    ("language", "consent", "give"),
    [
        ("en", "Consent (Art. 9 GDPR) to drafts", "Give this consent"),
        ("de", "Einwilligung (Art. 9 DSGVO) in Entwürfe", "Einwilligung erteilen"),
    ],
)
def test_the_consent_names_its_purpose_and_recipients_and_is_given_in_one_click(
    monkeypatch, gymer_thread, fake_model, language, consent, give
):
    """The text names OpenRouter and the provider; one click gives it; no draft button before."""
    at = _run(monkeypatch, language=language)
    page = texts(at)
    assert consent in page and "OpenRouter" in page and "OpenAI" in page
    assert give in _labels(at)
    assert not any("Draft entries" in label or "entwerfen" in label for label in _labels(at))
    _button(at, give).click()
    at.run(timeout=30)
    with db.connect() as conn:
        assert ai_consents.is_given(conn, USER_ID, drafting.PURPOSE, drafting.consent_version())
    assert fake_model.calls == []  # giving consent drafts nothing on its own


@pytest.mark.parametrize(
    ("language", "label", "button", "save"),
    [
        ("en", "Drafted by an AI model", "Draft entries from my messages", "Save decisions"),
        (
            "de",
            "Von einem KI-Modell",
            "Einträge aus meinen Nachrichten entwerfen",
            "Entscheidungen speichern",
        ),
    ],
)
def test_cards_say_they_are_ai_drafts_and_log_only_when_saved(
    monkeypatch, gymer_thread, fake_model, language, label, button, save
):
    """The press shows labelled cards; nothing is logged until the step is saved."""
    _consent()
    meals, weights = _logged("meal_items"), _logged("body_measurements")
    at = _run(monkeypatch, language=language)
    assert fake_model.calls == []  # never on a page load
    _button(at, button).click()
    at.run(timeout=30)
    assert len(fake_model.calls) == 1
    assert any(label in str(box.value) for box in at.info)
    assert (_logged("meal_items"), _logged("body_measurements")) == (meals, weights)
    _decide(at, "approve", "approve")
    [form_button] = [item for item in at.button if item.label == save]
    form_button.click()
    at.run(timeout=30)
    assert (_logged("meal_items"), _logged("body_measurements")) == (meals + 1, weights + 1)


def test_a_rejected_card_is_not_logged(monkeypatch, gymer_thread, fake_model):
    """Rejecting the weight card logs only the food."""
    _consent()
    weights = _logged("body_measurements")
    at = _run(monkeypatch)
    _button(at, "Draft entries from my messages").click()
    at.run(timeout=30)
    _decide(at, "approve", "reject")
    _button(at, "Save decisions").click()
    at.run(timeout=30)
    assert _logged("body_measurements") == weights
    assert "Saved. Entries logged: 1." in _success(at)


def test_withdrawing_the_consent_drops_the_pending_cards(monkeypatch, gymer_thread, fake_model):
    """A withdrawal removes the cards at once and logs nothing."""
    _consent()
    meals = _logged("meal_items")
    at = _run(monkeypatch)
    _button(at, "Draft entries from my messages").click()
    at.run(timeout=30)
    assert "Save decisions" in _labels(at)
    _button(at, "Withdraw this consent").click()
    at.run(timeout=30)
    assert "Save decisions" not in _labels(at)
    assert "Give this consent" in _labels(at)
    assert _logged("meal_items") == meals


def test_a_coach_sees_no_drafts(monkeypatch):
    """The coach's Messages page has neither the consent nor the button."""
    store_account("coach", "Coach Sam")
    _user("gym-mia", "gymer", "Mia")
    _pair(USER_ID, "gym-mia")
    at = _run(monkeypatch)
    assert "Consent (Art. 9 GDPR)" not in texts(at)
    assert not any("Draft entries" in label for label in _labels(at))


def test_a_missing_instruction_says_so_and_calls_no_model(
    monkeypatch, gymer_thread, fake_model, tmp_path
):
    """Without the owner's instruction file the press shows the fixed message, with no call."""
    _consent()
    monkeypatch.setattr(config, "DRAFT_PROMPT_PATH", tmp_path / "missing.md")
    at = _run(monkeypatch)
    _button(at, "Draft entries from my messages").click()
    at.run(timeout=30)
    assert "draft_entries_system.md" in "\n".join(str(item.value) for item in at.error)
    assert fake_model.calls == []


def test_a_card_has_no_choice_until_the_gymer_picks_one(monkeypatch, gymer_thread, fake_model):
    """Saving with a card left undecided logs nothing and asks again."""
    _consent()
    meals = _logged("meal_items")
    at = _run(monkeypatch)
    _button(at, "Draft entries from my messages").click()
    at.run(timeout=30)
    actions = [item for item in at.button_group if item.label == "Decision"]
    assert [action.value for action in actions] == [None, None]
    _decide(at, "approve", None)
    _button(at, "Save decisions").click()
    at.run(timeout=30)
    assert _logged("meal_items") == meals
    assert "Decide every card" in "\n".join(str(item.value) for item in at.error)
    assert "Save decisions" in _labels(at)


def test_approving_a_changed_card_logs_the_values_shown(monkeypatch, gymer_thread, fake_model):
    """Grams changed under Change the values and then approved are logged as changed."""
    _consent()
    at = _run(monkeypatch)
    _button(at, "Draft entries from my messages").click()
    at.run(timeout=30)
    [grams] = [item for item in at.number_input if item.label == "Grams"]
    grams.set_value(150.0)
    _decide(at, "approve", "reject")
    _button(at, "Save decisions").click()
    at.run(timeout=30)
    with db.connect() as conn:
        row = conn.execute(
            "SELECT food_name, grams FROM meal_items WHERE user_id = ? ORDER BY id DESC",
            (USER_ID,),
        ).fetchone()
    assert (row["food_name"], row["grams"]) == (EGG, 150.0)
    assert "Saved. Entries logged: 1." in _success(at)


def _press(at: AppTest) -> None:
    """Press the draft button and run the page."""
    _button(at, "Draft entries from my messages").click()
    at.run(timeout=30)


def test_a_press_counts_against_the_session_limit(monkeypatch, gymer_thread, fake_model):
    """With the session's limit reached, a press says so and calls no model."""
    _consent()
    limiter = guard.RateLimiter(per_session=1)
    assert limiter.try_acquire() is None
    monkeypatch.setattr(guard, "session_limiter", lambda state: limiter)
    at = _run(monkeypatch)
    _press(at)
    assert fake_model.calls == []
    assert "limit of 1 requests" in "\n".join(str(item.value) for item in at.warning)


def test_a_model_error_shows_its_own_text_and_that_nothing_was_logged(monkeypatch, gymer_thread):
    """A rejected key shows the key's text and the note that nothing more was logged."""
    fake = ScriptedTranslator(plans=[llm.InvalidAPIKeyError(401)], model_name=config.DRAFT_MODEL)
    monkeypatch.setattr(resources, "draft_model", lambda: fake)
    _consent()
    at = _run(monkeypatch)
    _press(at)
    assert "API key was rejected" in "\n".join(str(item.value) for item in at.error)
    assert "Nothing more was logged" in "\n".join(str(item.value) for item in at.info)


def test_a_card_shows_what_approve_saves(monkeypatch, gymer_thread, fake_model):
    """The food card shows its grams, day, meal slot and the AI's reading, and the run's place."""
    _consent()
    at = _run(monkeypatch)
    _press(at)
    captions = "\n".join(str(item.value) for item in at.caption)
    assert "100 g · Day:" in captions
    assert "Read by the AI as: Egg, whole, raw, frozen, pasteurized" in captions
    assert "Message 1 of 1 in this run" in captions
    [meal] = [item for item in at.selectbox if item.label == "Meal"]
    assert meal.value == "breakfast"


def test_a_workout_card_is_logged_as_shown_or_as_changed(monkeypatch, gymer_thread):
    """An unchanged workout card logs its sets; changed reps are logged as changed."""
    workout = [{"exercise_id": "squat", "sets": 2, "reps": 5, "weight": 100.0, "unit": "kg"}]
    reply = json.dumps({"foods": [], "weight": None, "workout": workout})
    fake = ScriptedTranslator(plans=[reply, reply], model_name=config.DRAFT_MODEL)
    monkeypatch.setattr(resources, "draft_model", lambda: fake)
    _consent()
    sessions = _logged("workout_sessions")
    at = _run(monkeypatch)
    _press(at)
    _decide(at, "approve")
    _button(at, "Save decisions").click()
    at.run(timeout=30)
    assert _logged("workout_sessions") == sessions + 1
    with db.connect() as conn:
        thread = conn.execute("SELECT id FROM coach_clients").fetchone()[0]
        messages.send_message(conn, USER_ID, thread, "Squats again, 2 x 8.")
    _press(at)
    [first, *_] = [item for item in at.number_input if item.label == "Reps"]
    first.set_value(8)
    _decide(at, "approve")
    _button(at, "Save decisions").click()
    at.run(timeout=30)
    with db.connect() as conn:
        reps = conn.execute(
            "SELECT exercise_set.reps FROM exercise_sets AS exercise_set"
            " JOIN workout_sessions AS session ON session.id = exercise_set.session_id"
            " WHERE session.user_id = ? ORDER BY exercise_set.id DESC LIMIT 2",
            (USER_ID,),
        ).fetchall()
    assert sorted(row[0] for row in reps) == [5, 8]


def test_a_run_of_an_ended_relationship_is_dropped_on_the_page(
    monkeypatch, gymer_thread, fake_model
):
    """Once the coach ends it and the gymer has a new coach, the old run's cards are gone."""
    _consent()
    at = _run(monkeypatch)
    _press(at)
    assert "Save decisions" in _labels(at)
    _user("coach-new", "coach", "Coach New")
    with db.connect() as conn:
        users.end_relationship(conn, COACH, gymer_thread)
        users.start_relationship(conn, "coach-new", USER_ID)
    at.run(timeout=30)
    assert "Save decisions" not in _labels(at)
    assert "Draft entries from my messages" in _labels(at)


def test_cards_already_drafted_are_saved_if_the_instruction_file_is_gone(
    monkeypatch, gymer_thread, fake_model, tmp_path
):
    """A decision resumes with the run's own instruction, so a missing file blocks no save."""
    _consent()
    meals = _logged("meal_items")
    at = _run(monkeypatch)
    _press(at)
    monkeypatch.setattr(config, "DRAFT_PROMPT_PATH", tmp_path / "missing.md")
    _decide(at, "approve", "reject")
    _button(at, "Save decisions").click()
    at.run(timeout=30)
    assert _logged("meal_items") == meals + 1


def test_a_run_is_dropped_when_the_page_shows_its_ended_thread(
    monkeypatch, gymer_thread, fake_model
):
    """With no other coach, the ended thread's page forgets the paused run and its messages."""
    _consent()
    at = _run(monkeypatch)
    _press(at)
    assert "Save decisions" in _labels(at)
    drafter = at.session_state[f"drafts_drafter_{USER_ID}"]
    thread_id = drafter.thread_id
    with db.connect() as conn:
        users.end_relationship(conn, COACH, gymer_thread)
    at.run(timeout=30)
    assert "Save decisions" not in _labels(at)
    assert drafter.thread_id is None and drafter.relationship_id is None
    saved = drafter.checkpointer.get_tuple({"configurable": {"thread_id": thread_id}})
    assert saved is None


def test_a_meal_picked_on_the_card_is_logged(monkeypatch, gymer_thread):
    """A food with no meal named gets its slot from the card's own picker, no expander needed."""
    reply = json.dumps(
        {"foods": [{"food": EGG, "grams": 100.0, "meal": None}], "weight": None, "workout": []}
    )
    fake = ScriptedTranslator(plans=[reply], model_name=config.DRAFT_MODEL)
    monkeypatch.setattr(resources, "draft_model", lambda: fake)
    _consent()
    at = _run(monkeypatch)
    _press(at)
    [meal] = [item for item in at.selectbox if item.label == "Meal"]
    assert meal.value is None
    meal.set_value("dinner")
    _decide(at, "approve")
    _button(at, "Save decisions").click()
    at.run(timeout=30)
    with db.connect() as conn:
        row = conn.execute(
            "SELECT meal FROM meal_items WHERE user_id = ? ORDER BY id DESC", (USER_ID,)
        ).fetchone()
    assert row["meal"] == "dinner"


def test_the_progress_line_counts_the_messages_passed_over(monkeypatch, gymer_thread):
    """A message with no entry before the one shown is counted as passed over."""
    empty = json.dumps({"foods": [], "weight": None, "workout": []})
    fake = ScriptedTranslator(plans=[empty, _reply()], model_name=config.DRAFT_MODEL)
    monkeypatch.setattr(resources, "draft_model", lambda: fake)
    with db.connect() as conn:
        messages.send_message(conn, USER_ID, gymer_thread, "Two eggs and 74 kg again.")
    _consent()
    at = _run(monkeypatch)
    _press(at)
    captions = "\n".join(str(item.value) for item in at.caption)
    assert "Message 2 of 2 in this run · 1 passed over" in captions


def test_the_ai_reading_of_a_food_is_shown_escaped(monkeypatch, gymer_thread):
    """The model's food name is shown on one line with Markdown escaped, never as a link."""
    asked = "oats [tap](https://example.com) $x$\n# Big"
    reply = json.dumps(
        {"foods": [{"food": asked, "grams": 80.0, "meal": None}], "weight": None, "workout": []}
    )
    fake = ScriptedTranslator(plans=[reply], model_name=config.DRAFT_MODEL)
    monkeypatch.setattr(resources, "draft_model", lambda: fake)
    _consent()
    at = _run(monkeypatch)
    _press(at)
    [line] = [str(item.value) for item in at.caption if "Read by the AI as" in str(item.value)]
    assert "\\[tap\\]" in line and "\\$x\\$" in line
    assert "\n" not in line and "](https" not in line.replace("\\]", "")


def test_the_consent_can_be_withdrawn_with_only_an_ended_thread(monkeypatch, gymer_thread):
    """With no active coach the consent still shows with its withdraw button, and it works."""
    _consent()
    with db.connect() as conn:
        users.end_relationship(conn, COACH, gymer_thread)
    at = _run(monkeypatch)
    assert "Draft entries from my messages" not in _labels(at)
    _button(at, "Withdraw this consent").click()
    at.run(timeout=30)
    with db.connect() as conn:
        assert ai_consents.current(conn, USER_ID, drafting.PURPOSE) is None
    assert "Withdraw this consent" not in _labels(at)


def test_the_consent_can_be_withdrawn_with_no_conversation(monkeypatch):
    """A gymer with no relationship at all still sees and withdraws a consent they gave."""
    store_account("gymer", "Mia", profile=PROFILE)
    _consent()
    at = _run(monkeypatch)
    _button(at, "Withdraw this consent").click()
    at.run(timeout=30)
    with db.connect() as conn:
        assert ai_consents.current(conn, USER_ID, drafting.PURPOSE) is None


@pytest.mark.parametrize(
    ("language", "others", "coach"),
    [
        ("en", "other people's names included", "your conversation with your current coach"),
        ("de", "auch Namen anderer Personen", "im Gespräch mit Ihrem aktuellen Coach"),
    ],
)
def test_the_consent_text_says_other_names_go_too_and_names_the_current_coach(
    monkeypatch, gymer_thread, fake_model, language, others, coach
):
    """Consent (a) tells the gymer that other people's names in a message are sent too."""
    at = _run(monkeypatch, language=language)
    page = texts(at)
    assert others in page and coach in page


def test_a_food_already_logged_that_day_is_flagged_on_its_card(
    monkeypatch, gymer_thread, fake_model
):
    """The same food logged by hand in the same meal and day shows a note; nothing is merged."""
    with db.connect() as conn:
        diary.log_food(
            conn, USER_ID, food_name=EGG, grams=50.0, meal="breakfast", day=metrics.berlin_day()
        )
    _consent()
    at = _run(monkeypatch)
    _press(at)
    notes = "\n".join(str(item.value) for item in at.warning)
    assert "Already logged on" in notes and "50 g (Breakfast)" in notes
    assert _logged("meal_items") == 1  # the note merges or changes nothing
