"""Drafting log entries from a gymer's own messages (T11.5, D26; `src/agent/drafts.py`)."""

from src.config.models import DEFAULT_ANSWER_MODEL, DEFAULT_MAX_TOKENS
from src.config.paths import PROJECT_ROOT

# The model that reads one message and returns its entries with structured output (on the
# allowlist, built by build_chat_model()), and its token cap.
DRAFT_MODEL = DEFAULT_ANSWER_MODEL
DRAFT_MAX_TOKENS = DEFAULT_MAX_TOKENS
# The only providers OpenRouter may route the draft model to, with no fallback: consent (a)'s
# text names them (OpenRouter serves this model from OpenAI and from Azure). The slug is
# OpenRouter's; `drafting.model_provider()` gives the name the text shows.
DRAFT_PROVIDERS: tuple[str, ...] = ("openai",)
# The owner's instruction (owner task O19); the page says it is missing until the file has text.
DRAFT_PROMPT_PATH = PROJECT_ROOT / "src" / "prompts" / "draft_entries_system.md"
DRAFT_PROMPT_MISSING_MESSAGE = (
    "The instruction for drafting log entries (`src/prompts/draft_entries_system.md`) is missing "
    "or empty, so no entry can be drafted. Restore the file and try again."
)
# One press of the button reads at most this many of the gymer's undrafted messages, oldest first,
# one model call each; the next press goes on with the rest.
DRAFT_MAX_MESSAGES_PER_RUN = 10
# How much of a message's reply becomes cards: foods, groups of identical sets, and the sets in a
# group. More is dropped in code and counted.
DRAFT_MAX_FOODS = 10
DRAFT_MAX_SET_GROUPS = 10
DRAFT_MAX_SETS_PER_GROUP = 10
# The step limit of one run: up to four nodes per message (next, extract, decide, save), twice
# that for decisions asked again, and slack.
DRAFT_MAX_STEPS = 8 * DRAFT_MAX_MESSAGES_PER_RUN + 10
