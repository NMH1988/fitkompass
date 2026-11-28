"""lookup_food_nutrition: nutrients of a food and amount, from the USDA Foundation Foods table.

The table (`data/usda_foods.csv`) is made by `scripts/prepare_usda.py` from USDA FoodData Central
(CC0 1.0; docs/SOURCES.md #21). The chat's tool (`lookup_food_nutrition`) scores food names with
rapidfuzz after folding case, punctuation and simple plurals, and takes a name as the match only
when it also shares a word with the query that names the food (`_names_the_food()`); a misspelt
name is usually "not found", with the closest names as suggestions. The matched USDA name and close
alternatives are always returned, so the model and the user can see what was looked up. The Food
lookup tab's dropdown (`food_names`, `lookup_chosen_food`, T4.8) takes only the table's own names
and looks them up exactly, with no alternatives.
"""

import csv
import re
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Literal, NamedTuple, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from rapidfuzz import fuzz, process, utils

from src import config, i18n
from src.i18n import Language

# The columns of data/usda_foods.csv; values are per 100 g of the food as described.
TABLE_COLUMNS: tuple[str, ...] = (
    "fdc_id",
    "description",
    "kcal",
    "protein_g",
    "carbohydrate_g",
    "fat_g",
    "fiber_g",
)
SOURCE = "USDA FoodData Central, Foundation Foods (CC0 1.0), https://fdc.nal.usda.gov/"
# The release date in the table's credit line (config.USDA_CITATION).
RELEASE_IN_CREDIT = re.compile(r"Foundation Foods, release (\d{4}-\d{2}-\d{2})\.")
# Words that mark a processed form of a food ("Flour, almond", "Oat milk", "Egg, yolk, dried").
# A name with one the query does not ask for ranks below the plain food.
FORM_WORDS = frozenset({"flour", "oil", "juice", "dried", "powder", "milk", "butter"})


class FoodTableError(RuntimeError):
    """The foods table is missing or does not have the expected columns and values."""


class Food(BaseModel):
    """One row of the foods table: a USDA food and its nutrients per 100 g."""

    model_config = ConfigDict(frozen=True)

    fdc_id: int = Field(gt=0)
    description: str = Field(min_length=1)
    kcal: float = Field(ge=0)
    protein_g: float = Field(ge=0)
    carbohydrate_g: float = Field(ge=0)
    fat_g: float = Field(ge=0)
    # None when USDA reports no fiber value for the food ("not reported", not zero).
    fiber_g: float | None = Field(default=None, ge=0)


class FoodLookupArgs(BaseModel):
    """The tool's arguments, as the model sends them; checked before any lookup."""

    # extra="forbid": a call with any other field (e.g. `table`, the tests' hook) is refused.
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    food: str = Field(
        min_length=config.FOOD_MIN_NAME_CHARS,
        max_length=config.FOOD_MAX_NAME_CHARS,
        # A bare "chicken" or "rice" matches one variant chosen by name, not by nutrition. The word
        # rule below is not in the JSON schema the model sees, so the description states it.
        description=(
            "One food in plain English, with at least one real word (2 or more letters), as "
            "specific as possible (cut, form, raw or cooked), e.g. 'chicken breast skinless raw' "
            "or 'rolled oats'. Translate a food named in another language into English first "
            "(e.g. 'Hähnchenbrust' as 'chicken breast')."
        ),
    )
    # Strict: a JSON number only (no strings or booleans); an int is accepted.
    grams: float = Field(
        ge=config.FOOD_MIN_GRAMS,
        le=config.FOOD_MAX_GRAMS,
        allow_inf_nan=False,
        strict=True,
        description="Amount of the food in grams.",
    )

    @field_validator("food")
    @classmethod
    def _has_a_real_word(cls, value: str) -> str:
        """Refuse a name whose longest word, once punctuation is dropped, is too short."""
        # "a.", "-a" or "a a" would otherwise match "Eggs, Grade A" by chance. Checked here, not
        # after validation, so a bad name and bad grams are reported together.
        if max((len(word) for word in _normalise(value).split()), default=0) < (
            config.FOOD_MIN_NAME_CHARS
        ):
            raise ValueError("no word is long enough")
        return value


class Nutrients(BaseModel):
    """Nutrients in the requested amount of a food."""

    kcal: int
    protein_g: float
    carbohydrate_g: float
    fat_g: float
    # None when USDA reports no fiber value for the food.
    fiber_g: float | None


# What happened when the chat's food tool asked the USDA FoodData Central API (T9.9): it found the
# food, found no close match, did not send the name (not plain English words), had used up the
# turn's searches, or failed (the request timed out, the service was down, the key's quota was used
# up, the key was refused, or the answer could not be read).
ApiCode = Literal[
    "found",
    "no_match",
    "name_refused",
    "turn_limit",
    "timeout",
    "unavailable",
    "rate_limited",
    "key_rejected",
    "bad_response",
]


class FoodLookupResult(BaseModel):
    """What the tool returns: the scaled nutrients of the matched food, or why there are none."""

    status: Literal["found", "not_found", "invalid"]
    message: str
    grams: float | None = None
    matched_name: str | None = None
    fdc_id: int | None = None
    nutrients: Nutrients | None = None
    # Other close USDA names when found; "did you mean" suggestions when not found.
    alternatives: list[str] = Field(default_factory=list)
    source: str = SOURCE
    # Where the values came from (T9.9): the committed Foundation Foods table, or the FoodData
    # Central API, with the USDA data type of the food it found (one of FOOD_API_DATA_TYPES).
    origin: Literal["table", "api"] = "table"
    data_type: str | None = None
    # None when the API was not asked (a match in the table, no key, or not the chat's tool).
    api_code: ApiCode | None = None


def food_source_line(result: FoodLookupResult, lang: Language) -> str:
    """Return the line under a found food's values: the table's source, or the API's (T9.9)."""
    # Shared by the tool results in the app and the summary PDF, so both credit the same data.
    if result.origin == "api":
        return i18n.t("usda.api_source_line", lang, data_type=result.data_type or "")
    return i18n.t("usda.source_line", lang)


def read_usda_release(path: Path | None = None) -> str:
    """Return the USDA release date (YYYY-MM-DD) named in the foods table's credit line."""
    path = path or config.USDA_FOODS_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FoodTableError(
            f"{path.name} is missing; run python scripts/prepare_usda.py to make it."
        ) from None
    credit = " ".join(line for line in text.splitlines() if line.startswith("#"))
    match = RELEASE_IN_CREDIT.search(credit)
    if match is None:
        raise FoodTableError(f"{path.name} does not name its USDA release.")
    return match.group(1)


def load_food_table(path: Path | None = None) -> tuple[Food, ...]:
    """Return the foods in the table (read once per path, then cached)."""
    return _load_food_table(path or config.USDA_FOODS_PATH)


@lru_cache(maxsize=4)
def _load_food_table(path: Path) -> tuple[Food, ...]:
    """Read and validate the foods table, skipping the '#' credit lines at the top."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FoodTableError(
            f"{path.name} is missing; run python scripts/prepare_usda.py to make it."
        ) from None
    reader = csv.DictReader(line for line in text.splitlines() if not line.startswith("#"))
    if tuple(reader.fieldnames or ()) != TABLE_COLUMNS:
        raise FoodTableError(f"{path.name} does not have the columns {', '.join(TABLE_COLUMNS)}.")
    foods = []
    for number, row in enumerate(reader, start=1):
        try:
            foods.append(Food(**{key: (value or None) for key, value in row.items()}))
        except ValidationError, TypeError:
            raise FoodTableError(f"{path.name}: row {number} is not valid.") from None
    if not foods:
        raise FoodTableError(f"{path.name} has no foods.")
    return tuple(foods)


def _normalise(text: str) -> str:
    """Lower-case the text, drop punctuation and reduce simple plurals, for name matching."""
    words = []
    for word in utils.default_process(text).split():
        if len(word) > 3 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 3 and word.endswith("oes"):
            word = word[:-2]
        elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        words.append(word)
    return " ".join(words)


def _score(query: str, choice: str, **_: object) -> float:
    """Score a name 0-100: the mean of overall similarity and "all query words are in it"."""
    # WRatio alone ranks "tuna" closer to "butter"; token_set_ratio alone gives "banana" a
    # perfect score for "Peppers, banana"; their mean worked best on the real table (T4.3).
    return (fuzz.WRatio(query, choice) + fuzz.token_set_ratio(query, choice)) / 2


def _names_the_food(query_words: set[str], name: str) -> bool:
    """Return whether a query word naming a food is among the name's words before a qualifier."""
    # `name` is normalised. Preparation words (config.FOOD_PREPARATION_WORDS) never name the food,
    # and what follows "with", "in", "without" or "and" is an ingredient or a note, not the food:
    # "olive oil" is not "Anchovies, canned in olive oil", "boiled eggs" not "Kale, ..., boiled".
    food_words = query_words - config.FOOD_PREPARATION_WORDS
    for word in name.split():
        if word in config.FOOD_QUALIFIER_WORDS:
            return False
        if word in food_words:
            return True
    return False


class _Ranked(NamedTuple):
    """One food of a ranking, and whether it counts as the match (score and word check passed)."""

    food: Food
    is_match: bool


def _rank(query: str, foods: Sequence[Food]) -> list[_Ranked]:
    """Return the foods scoring at least the suggestion threshold, the matches first, best first."""
    # A match scores at least FOOD_MATCH_MIN_SCORE and names the food (_names_the_food()). The score
    # alone favours short names too much ("milk" scores higher on "Yogurt, plain, whole milk" than
    # on "Milk, whole, 3.25% milkfat"), so the foods are ordered by these, in turn:
    # 1. the matches first;
    # 2. a name that names the food before one that does not, so "boiled eggs", which matches
    #    nothing, suggests the egg names before the boiled kale;
    # 3. a name scoring at least the match threshold before one that does not;
    # 4. the plain food before a processed form the query does not name (FORM_WORDS): "Nuts,
    #    almonds" before "Flour, almond" and "Almond butter" for "almonds";
    # 5. a name whose head (before the first comma) is made only of query words, since USDA names
    #    lead with the food itself: for "white rice", "Rice, white" is rice, "Flour, rice" flour;
    # 6. the higher token_set_ratio (how fully the query words appear in the name);
    # 7. the higher score, then the shorter, plainer name.
    names = [_normalise(f.description) for f in foods]
    hits = process.extract(
        query,
        names,
        scorer=_score,
        limit=None,
        score_cutoff=config.FOOD_SUGGESTION_MIN_SCORE,
    )
    query_words = set(query.split())
    checked = [(hit, _names_the_food(query_words, hit[0])) for hit in hits]

    def is_match(score: float, names_food: bool) -> bool:
        """Return whether a name with this score and word check counts as the match."""
        return names_food and score >= config.FOOD_MATCH_MIN_SCORE

    def order(
        item: tuple[tuple[str, float, int], bool],
    ) -> tuple[bool, bool, bool, bool, bool, int, float, int]:
        """Sort key for one hit: the preferences listed above, in turn."""
        (name, score, index), names_food = item
        head = set(_normalise(foods[index].description.split(",")[0]).split())
        return (
            not is_match(score, names_food),
            not names_food,
            score < config.FOOD_MATCH_MIN_SCORE,
            bool((set(name.split()) & FORM_WORDS) - query_words),
            not head <= query_words,
            -round(fuzz.token_set_ratio(query, name)),
            -score,
            len(name),
        )

    return [
        _Ranked(foods[index], is_match(score, names_food))
        for (_, score, index), names_food in sorted(checked, key=order)
    ]


def _scale(food: Food, grams: float) -> Nutrients:
    """Scale the food's per-100 g values to the given amount, rounded for display."""
    factor = grams / 100
    digits = config.FOOD_DECIMALS
    return Nutrients(
        kcal=round(food.kcal * factor),
        protein_g=round(food.protein_g * factor, digits),
        carbohydrate_g=round(food.carbohydrate_g * factor, digits),
        fat_g=round(food.fat_g * factor, digits),
        fiber_g=None if food.fiber_g is None else round(food.fiber_g * factor, digits),
    )


def invalid_lookup_message(error: ValidationError) -> str:
    """State which arguments are wrong, as facts, without repeating what was sent."""
    fields = {str(e["loc"][0]) for e in error.errors() if e["loc"]}
    parts = lookup_problems(fields)
    return (
        "Invalid food lookup: " + ("; ".join(parts) or "the arguments do not fit the schema") + "."
    )


def lookup_problems(fields: set[str]) -> list[str]:
    """Return what is wrong with a food and grams pair, given the names of the failed fields."""
    parts = []
    if fields - set(FoodLookupArgs.model_fields):
        # Never names the extra field: it is the model's text.
        parts.append("only the arguments food and grams are accepted")
    if "food" in fields:
        parts.append(
            f"food must be the name of one food in {config.FOOD_MIN_NAME_CHARS} to "
            f"{config.FOOD_MAX_NAME_CHARS} characters, with at least one word of "
            f"{config.FOOD_MIN_NAME_CHARS} or more letters or digits"
        )
    if "grams" in fields:
        parts.append(
            f"the amount must be a number of grams from {config.FOOD_MIN_GRAMS:g} to "
            f"{config.FOOD_MAX_GRAMS}"
        )
    return parts


def lookup_food_nutrition(
    food: str, grams: float, table: Sequence[Food] | None = None
) -> FoodLookupResult:
    """Return the nutrients of the named food for the given grams, or a clear message why not."""
    # Invalid arguments and unknown foods give a result, never an exception; a missing or broken
    # table raises FoodTableError, which the tool wrapper (src/tools/registry.py) turns into a
    # tool error message. `table` replaces the committed foods table (tests); it is never a model
    # argument (the tool's args_schema is FoodLookupArgs).
    try:
        args = FoodLookupArgs(food=food, grams=grams)
    except ValidationError as exc:
        return FoodLookupResult(status="invalid", message=invalid_lookup_message(exc))

    query = _normalise(args.food)
    foods = load_food_table() if table is None else table
    ranked = _rank(query, foods)
    limit = config.FOOD_MAX_ALTERNATIVES

    if not ranked or not ranked[0].is_match:
        suggestions = [r.food.description for r in ranked[:limit]]
        message = "No close match in the USDA Foundation Foods table."
        if suggestions:
            message += " Did you mean one of the alternatives? They are the closest names in it."
        else:
            message += (
                " No similar name: the table holds single, unprocessed foods under plainer names "
                "(e.g. 'rolled oats')."
            )
        return FoodLookupResult(
            status="not_found", message=message, grams=args.grams, alternatives=suggestions
        )

    others = [r.food.description for r in ranked[1 : 1 + limit]]
    return _found(ranked[0].food, args.grams, others)


def _found(
    food: Food, grams: float, alternatives: list[str], data_type: str | None = None
) -> FoodLookupResult:
    """Return the "found" result for this food and amount; data_type for a food from the API."""
    message = f"{grams:g} g of {food.description}, from per-100 g USDA values."
    if data_type is not None:
        message = (
            "Not in the USDA Foundation Foods table; found through the USDA FoodData Central API "
            f"({data_type}): {message}"
        )
    if food.fiber_g is None:
        message += " USDA reports no fiber value for this food."
    extra = {}
    if data_type is not None:
        extra = {
            "source": config.FOOD_API_SOURCE.format(data_type=data_type),
            "origin": "api",
            "data_type": data_type,
            "api_code": "found",
        }
    return FoodLookupResult(
        status="found",
        message=message,
        grams=grams,
        matched_name=food.description,
        fdc_id=food.fdc_id,
        nutrients=_scale(food, grams),
        alternatives=alternatives,
        **extra,
    )


def food_names(table: Sequence[Food] | None = None) -> tuple[str, ...]:
    """Return the names of the foods in the table, sorted, for the Food lookup tab's dropdown."""
    foods = load_food_table() if table is None else table
    return tuple(sorted((food.description for food in foods), key=str.casefold))


def lookup_chosen_food(
    name: object, grams: object, table: Sequence[Food] | None = None
) -> FoodLookupResult:
    """Return the nutrients of the food with exactly this name, chosen from the dropdown (T4.8)."""
    # No fuzzy matching and no length limit on the name: it is one of the table's own names (two
    # are longer than FOOD_MAX_NAME_CHARS, which limits free text). Anything else is invalid.
    foods = load_food_table() if table is None else table
    chosen = next((food for food in foods if food.description == name), None)
    # A number only (no strings or booleans); NaN fails both comparisons.
    grams_ok = (
        isinstance(grams, int | float)
        and not isinstance(grams, bool)
        and config.FOOD_MIN_GRAMS <= grams <= config.FOOD_MAX_GRAMS
    )
    if chosen is None or not grams_ok:
        parts = ["choose one food from the list"] if chosen is None else []
        parts += [] if grams_ok else lookup_problems({"grams"})
        return FoodLookupResult(
            status="invalid", message="Invalid food lookup: " + "; ".join(parts) + "."
        )
    return _found(chosen, float(cast(float, grams)), [])
