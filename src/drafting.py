"""Draft log entries from one of a gymer's own messages, checked in code (T11.5, feature 31, D26).

The model reads one message, delimited as data, and returns `DraftEntries` with structured output:
the foods it names (a plain English name, the grams and the meal slot when the message states
them), the gymer's own weight, and groups of identical sets of an exercise from the app's fixed
list. Nothing it returns is stored as it is: `cards_from()` matches each food to the USDA table
(the card names the table's food, or none with the closest names to pick from), converts pounds to
kg, and keeps only exercises of the list and numbers within the workout log's ranges; the rest is
dropped and counted. A card's nutrients are worked out from the table's values, never from the
model's text. The one piece of the model's own text a card shows is a food's name as the model
wrote it (`asked`), to the gymer who wrote the message only: on one line, at most
`config.FOOD_MAX_NAME_CHARS` characters, escaped for Markdown on the page, never stored or logged,
and masked in a trace. `decided_entries()` turns the gymer's decisions on a message's cards
(approve, edit, reject) into the store's entries with the diary's own checks, so an approved entry
is stored as a hand-logged one is.

The consent this flow needs is (a), `PURPOSE` (`docs/PRD.md`, "Consents"); its text's version is
worked out from the English and German texts the gymer reads, so a changed text asks again.
"""

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any, Literal, get_args

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from src import chat, config, diary, exercises, i18n, llm, metrics, units
from src.prompt_data import escape_prompt_data
from src.store import drafts, records
from src.tools.food import Food, load_food_table, lookup_food_nutrition

# Consent (a) of the PRD: drafts of log entries from the gymer's own messages.
PURPOSE = "message_drafts"
CONSENT_TEXT_KEY = "drafts.consent_text"
Kind = Literal["food", "weight", "workout"]
KINDS: tuple[str, ...] = get_args(Kind)
Action = Literal["approve", "edit", "reject"]
ACTIONS: tuple[str, ...] = get_args(Action)
_MEALS: tuple[str, ...] = get_args(records.Meal)
# Grams for matching a food named with no amount: the match does not depend on them.
_MATCH_GRAMS = 100.0


class DraftError(ValueError):
    """A decision that cannot be logged; `code` is the i18n key of its message (never a value)."""

    def __init__(self, code: str) -> None:
        """Keep the message's key."""
        super().__init__(code)
        self.code = code


class FoodEntry(BaseModel):
    """A food the client says they ate, as the message names it."""

    model_config = ConfigDict(extra="forbid")

    food: str = Field(
        description=(
            "The food in plain English, as specific as the message allows (form, raw or cooked), "
            "e.g. 'rolled oats' or 'chicken breast cooked'; translate a food named in another "
            "language into English."
        )
    )
    grams: float | None = Field(
        description=(
            "The grams eaten, from an amount stated in g or kg (kg converted to g); null for any "
            "other amount or none."
        )
    )
    meal: records.Meal | None = Field(
        description="The meal the message names; null when it names none."
    )


class WeightEntry(BaseModel):
    """The client's own body weight, as the message states it."""

    model_config = ConfigDict(extra="forbid")

    value: float = Field(description="The body weight as written in the message.")
    unit: Literal["kg", "lb"] = Field(
        description="The unit the message uses for it; kg when the message gives no unit."
    )


class SetGroup(BaseModel):
    """Identical sets of one exercise the client says they did."""

    model_config = ConfigDict(extra="forbid")

    exercise_id: str = Field(
        description="The ID of the exercise in <exercises>, exactly as listed there."
    )
    sets: int = Field(
        description="How many identical sets the message names; 1 when it names no count."
    )
    reps: int = Field(description="The repetitions of each set.")
    weight: float = Field(description="The load of each set; 0 for body weight.")
    unit: Literal["kg", "lb"] = Field(
        description="The unit of the load; kg when the message gives no unit."
    )


class DraftEntries(BaseModel):
    """The log entries one message of the client names; empty when it names none."""

    model_config = ConfigDict(extra="forbid")

    foods: list[FoodEntry] = Field(description="The foods the client says they ate.")
    weight: WeightEntry | None = Field(
        description="The client's own body weight, when the message states it; else null."
    )
    workout: list[SetGroup] = Field(
        description="The sets the client says they did, of exercises in <exercises> only."
    )


def build_model(*, api_key: str | None = None, http_client: Any = None):
    """Build the draft model's client: its model, cap and the providers its consent names."""
    # The one place it is built (the workflow's default and the page's cached client), so the
    # provider pin that keeps consent (a)'s text true cannot be left out of either.
    return llm.build_chat_model(
        config.DRAFT_MODEL,
        config.DRAFT_MAX_TOKENS,
        providers=config.DRAFT_PROVIDERS,
        api_key=api_key,
        http_client=http_client,
    )


def consent_text(lang: i18n.Language) -> str:
    """Return consent (a)'s text in a language, naming OpenRouter and the model's provider."""
    return i18n.t(CONSENT_TEXT_KEY, lang, provider=model_provider())


def model_provider() -> str:
    """Return the name of the provider the draft model is pinned to, as the consent shows it."""
    names = {"openai": "OpenAI", "azure": "Microsoft Azure"}
    return " / ".join(names.get(slug, slug) for slug in config.DRAFT_PROVIDERS)


def consent_version() -> str:
    """Return the version of consent (a)'s text: both languages, so either changing asks again."""
    return chat.prompt_version(consent_text("en") + "\n" + consent_text("de"))


def message_day(created_at: str) -> date:
    """Return the Berlin day a message was sent on, from its stored UTC time."""
    return metrics.berlin_day(datetime.fromisoformat(created_at))


def _exercise_lines() -> str:
    """Return the exercise list the model may choose from: one ID and its names per line."""
    return "\n".join(
        f"{exercise.id}: {exercise.name['en']} / {exercise.name['de']}"
        for exercise in exercises.exercises()
    )


def build_messages(prompt_text: str, message_text: str) -> list[SystemMessage | HumanMessage]:
    """Return the model's input: the owner's instruction, then the lists and the message as data."""
    # The message is the client's text, escaped and delimited (a look-alike tag cannot close its
    # block) and never part of the system prompt; it reaches here only after the input guard and
    # the domain guardrails passed it.
    parts = [
        f"<meals>\n{', '.join(_MEALS)}\n</meals>",
        f"<exercises>\n{_exercise_lines()}\n</exercises>",
        f"<message>\n{escape_prompt_data(message_text)}\n</message>",
    ]
    return [SystemMessage(prompt_text), HumanMessage("\n\n".join(parts))]


def _grams(value: object) -> float | None:
    """Return grams within the food log's range, or None (the gymer fills them in)."""
    try:
        return diary.check_grams(value)
    except diary.DiaryError:
        return None


def _food_card(entry: FoodEntry, day: date, table: Sequence[Food]) -> dict | None:
    """Return a food card matched to the USDA table in code, or None if the name is unusable."""
    grams = _grams(entry.grams)
    found = lookup_food_nutrition(entry.food, grams or _MATCH_GRAMS, table)
    if found.status == "invalid":
        return None
    name = None
    if found.status == "found":
        name = next((food.description for food in table if food.fdc_id == found.fdc_id), None)
    return {
        "kind": "food",
        # The food as the model named it, on one line, shown beside the USDA match (never stored
        # or logged; masked in a trace).
        "asked": " ".join(entry.food.split()),
        "food_name": name,
        "grams": grams,
        "meal": entry.meal if entry.meal in _MEALS else None,
        "day": day.isoformat(),
        "alternatives": [alt for alt in found.alternatives if alt != name],
    }


def _kg(value: float, unit: str) -> float:
    """Return a weight in kg from the unit the message used."""
    return units.weight_to_kg(float(value), "imperial" if unit == "lb" else "metric")


def _weight_card(entry: WeightEntry, day: date) -> dict | None:
    """Return a weight card in kg within the profile's range, or None."""
    weight_kg = _kg(entry.value, entry.unit)
    low, high = config.PROFILE_WEIGHT_KG_RANGE
    if not low <= weight_kg <= high:  # NaN fails too
        return None
    return {"kind": "weight", "weight_kg": round(weight_kg, 1), "day": day.isoformat()}


def _sets(group: SetGroup, known: Sequence[str]) -> list[dict] | None:
    """Return a group's sets checked against the list and the workout log's ranges, or None."""
    low, high = config.WORKOUT_REPS_RANGE
    kg_low, kg_high = config.WORKOUT_WEIGHT_KG_RANGE
    weight_kg = _kg(group.weight, group.unit)
    if (
        group.exercise_id not in known
        or not 1 <= group.sets <= config.DRAFT_MAX_SETS_PER_GROUP
        or not low <= group.reps <= high
        or not kg_low <= weight_kg <= kg_high
    ):
        return None
    one = {"exercise_id": group.exercise_id, "reps": group.reps, "weight_kg": round(weight_kg, 1)}
    return [dict(one) for _ in range(group.sets)]


def _workout_card(groups: Sequence[SetGroup], day: date) -> tuple[dict | None, int]:
    """Return one workout card of the usable groups' sets and how many groups were dropped."""
    known = exercises.exercise_ids()
    sets: list[dict] = []
    dropped = max(0, len(groups) - config.DRAFT_MAX_SET_GROUPS)
    for group in groups[: config.DRAFT_MAX_SET_GROUPS]:
        found = _sets(group, known)
        if found is None or len(sets) + len(found) > config.WORKOUT_MAX_SETS:
            dropped += 1
            continue
        sets.extend(found)
    card = {"kind": "workout", "day": day.isoformat(), "sets": sets} if sets else None
    return card, dropped


def cards_from(
    entries: DraftEntries, day: date, table: Sequence[Food] | None = None
) -> tuple[list[dict], int]:
    """Return the cards of a reply, checked in code, and how many of its entries were dropped."""
    foods = load_food_table() if table is None else table
    cards: list[dict] = []
    dropped = max(0, len(entries.foods) - config.DRAFT_MAX_FOODS)
    for entry in entries.foods[: config.DRAFT_MAX_FOODS]:
        card = _food_card(entry, day, foods)
        if card is None:
            dropped += 1
        else:
            cards.append(card)
    if entries.weight is not None:
        card = _weight_card(entries.weight, day)
        if card is None:
            dropped += 1
        else:
            cards.append(card)
    card, lost = _workout_card(entries.workout, day)
    dropped += lost
    if card is not None:
        cards.append(card)
    return cards, dropped


def food_nutrients(card: Mapping[str, Any], table: Sequence[Food] | None = None) -> dict | None:
    """Return a food card's nutrients from the USDA table's values, or None if it is incomplete."""
    today = metrics.berlin_day()  # the day and meal do not change the values
    try:
        item = diary.checked_meal_item(
            card.get("food_name"), card.get("grams"), "snack", today, today, table
        )
    except diary.DiaryError:
        return None
    return {name: item[name] for name in metrics.NUTRIENTS}


def already_logged(card: Mapping[str, Any], logged: Sequence[Mapping]) -> list[dict]:
    """Return the gymer's entries of the card's food and day, in the card's meal if it names one."""
    # Shown on the card so the gymer sees a possible double entry (the food logged by hand on
    # Today and named again in a message) before approving; nothing is merged or changed.
    if card.get("kind") != "food" or not card.get("food_name"):
        return []
    return [
        {"food_name": item["food_name"], "grams": item["grams"], "meal": item["meal"]}
        for item in logged
        if item["food_name"] == card["food_name"]
        and item["consumed_on"] == card["day"]
        and (card.get("meal") is None or item["meal"] == card["meal"])
    ]


def _day(value: object, today: date) -> date:
    """Return a card's day if it is a date (or ISO text) within the diary's window."""
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError:
            raise diary.DiaryError("diary.day_range") from None
    return diary.check_day(value, today)


def _food(card: Mapping, today: date, table: Sequence[Food] | None) -> drafts.DraftedFood:
    """Return an approved food card as the store's entry, with the diary's checks."""
    day = _day(card.get("day"), today)
    item = diary.checked_meal_item(
        card.get("food_name"), card.get("grams"), card.get("meal"), day, today, table
    )
    return drafts.DraftedFood(**item)


def _weight(card: Mapping, today: date) -> drafts.DraftedWeight:
    """Return an approved weight card as the store's entry, in kg within the profile's range."""
    day = _day(card.get("day"), today)
    value = card.get("weight_kg")
    low, high = config.PROFILE_WEIGHT_KG_RANGE
    if isinstance(value, bool) or not isinstance(value, int | float) or not low <= value <= high:
        raise diary.DiaryError("diary.weight_range")
    return drafts.DraftedWeight(float(value), day)


def _workout(card: Mapping, today: date) -> drafts.DraftedWorkout:
    """Return an approved workout card as the store's entry; the store checks the sets again."""
    day = _day(card.get("day"), today)
    found = card.get("sets")
    if not isinstance(found, Sequence) or isinstance(found, str) or not found:
        raise DraftError("drafts.workout_invalid")
    sets = []
    for number, one in enumerate(found, start=1):
        if not isinstance(one, Mapping):
            raise DraftError("drafts.workout_invalid")
        sets.append(
            records.ExerciseSet(
                one.get("exercise_id"), number, one.get("reps"), one.get("weight_kg")
            )
        )
    return drafts.DraftedWorkout(day, tuple(sets))


def decided_entries(
    cards: Sequence[Mapping],
    decisions: object,
    today: date,
    table: Sequence[Food] | None = None,
) -> tuple[list[drafts.DraftedFood], list[drafts.DraftedWeight], list[drafts.DraftedWorkout]]:
    """Return the entries of a message's approved and edited cards; DraftError/DiaryError if bad."""
    # One decision per card, in order: every card of a message is decided in the same step.
    if (
        not isinstance(decisions, Sequence)
        or isinstance(decisions, str)
        or len(decisions) != len(cards)
    ):
        raise DraftError("drafts.decision_invalid")
    foods, weights, workouts = [], [], []
    for card, decision in zip(cards, decisions, strict=True):
        if not isinstance(decision, Mapping) or decision.get("action") not in ACTIONS:
            raise DraftError("drafts.decision_invalid")
        if decision["action"] == "reject":
            continue
        chosen = card if decision["action"] == "approve" else decision.get("card")
        if not isinstance(chosen, Mapping) or chosen.get("kind") != card["kind"]:
            raise DraftError("drafts.decision_invalid")
        if card["kind"] == "food":
            foods.append(_food(chosen, today, table))
        elif card["kind"] == "weight":
            weights.append(_weight(chosen, today))
        else:
            workouts.append(_workout(chosen, today))
    return foods, weights, workouts
