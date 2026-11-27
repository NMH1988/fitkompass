"""Drafts of log entries from a photo or a voice note, as a fixed LangGraph workflow (T11.10, D29).

read -> check (guard) -> extract -> decide (interrupt) -> save. Each step is fixed; the gymer starts
a run by pressing the button under a file they chose, and decides every card before anything is
logged, as in T11.5's workflow (`src/agent/drafts.py`), whose extraction, checks and cards it
reuses.

- **read** checks consent (c) to the text the gymer reads now and a saved profile, then makes the
  first model call: the owner's fixed instruction and the cleaned file only (`src/media.py`), no
  profile, message or name. It is the one model call no guard checks first, as the guard reads
  text. The file is in the run's context, never in its state, so no checkpoint holds it.
- **check** runs the input guard and the domain guardrails on the text the model returned
  (`guard.check_text()`, no model call); a refused text ends the run: no draft, no further call.
- **extract** checks consent (c) again right before the second call and sends that text, as
  data, with the owner's draft instruction (O19), as T11.5 does with a message; the reply becomes
  cards in code, dated the day the gymer picked on Today.
- **decide** pauses with `interrupt()` on the cards; **save** logs the approved entries in one
  store transaction (`drafts.save_entries()`), or pauses again with the code of a decision the
  diary's checks refuse.

The run is checkpointed in the session's memory only (`InMemorySaver`) and forgotten when it ends;
the file and the model's text are never written to disk, a log line or a trace: every run goes
inside `tracing.untraced()`, so not even demo mode's unmasked traces see them.
"""

import dataclasses
import logging
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

from src import account, chat, config, diary, drafting, guard, llm, media, metrics, tracing
from src.store import ai_consents, drafts, values
from src.store.access import NotFound
from src.tools.food import Food

logger = logging.getLogger(__name__)

# How a run ended, or that it waits for the gymer; the page shows a fixed text for each.
Outcome = Literal[
    "pending", "done", "nothing", "refused", "no_consent", "profile_first", "not_found", "error"
]
_RUN_ERRORS = (llm.LLMError, config.MissingAPIKeyError)
_SETUP_CODES: dict[type, str] = {
    config.SecretsFileError: "key.secrets_file",
    config.MissingAPIKeyError: "key.missing",
}


class MediaState(TypedDict, total=False):
    """A run's state, kept in the session's memory: the user, the kind, the day, text and cards."""

    user_id: str
    kind: media.Kind
    # The day the cards are dated (ISO), the one the gymer picked on Today.
    day: str
    # The model's description or transcript, once the guard passed it; shown above the cards and
    # forgotten with the run.
    text: str | None
    cards: list[dict]
    decision: dict | None
    # The i18n key of why the last decision could not be logged; the cards ask again.
    error: str | None
    refused: int
    cards_found: int
    dropped: int
    logged: int
    outcome: Outcome


@dataclass(frozen=True)
class MediaContext:
    """What the nodes use but never keep in state: the store, the file, the models and prompts."""

    store_path: Path
    # The owner's fixed instruction of the first call (O19) for this kind of file.
    media_prompt: chat.Prompt
    # The owner's draft instruction (O19, T11.5's), sent with the text the guard passed.
    draft_prompt: chat.Prompt
    # The first call's client for this kind of file, built only right before that call. No
    # default: a voice note must never fall back to the photo model.
    media_model: Callable[[], BaseChatModel]
    # The cleaned file (src/media.py); empty on a decision, which sends no file.
    file: bytes = b""
    # The version of consent (c)'s text the gymer reads now; a consent to another is none.
    consent_version: str = field(default_factory=media.consent_version)
    # The draft model, called only after the guard and the consent check passed.
    chat_model: Callable[[], BaseChatModel] = field(default=lambda: drafting.build_model())
    # The USDA table; None reads the committed one. Tests pass their own.
    food_table: Sequence[Food] | None = None
    # The day the run counts as today (Europe/Berlin); None for the real day. Tests set it.
    today: date | None = None
    # The ID of the run or decision in progress, for its log lines; set by MediaDrafter.
    turn_id: str = ""


@dataclass(frozen=True)
class RunResult:
    """How a run or decision ended (or waits), the cards to show while it waits, and its counts."""

    outcome: Outcome
    kind: media.Kind | None = None
    text: str | None = None
    cards: tuple[dict, ...] = ()
    error: str | None = None
    # Entries logged by this decision.
    logged: int = 0
    counts: Mapping[str, int] = field(default_factory=dict)
    error_code: str | None = None


def _today(context: MediaContext) -> date:
    """Return the run's today in Europe/Berlin."""
    return context.today or metrics.berlin_day()


def _consented(runtime: Runtime[MediaContext], user_id: str) -> bool:
    """Return whether the gymer's consent (c) to the current text holds, read from the store now."""
    with account.open_store(runtime.context.store_path) as conn:
        return ai_consents.is_given(conn, user_id, media.PURPOSE, runtime.context.consent_version)


def read(state: MediaState, runtime: Runtime[MediaContext]) -> dict[str, Any]:
    """Check consent (c) and the profile, then send the file alone with the fixed instruction."""
    user_id = state["user_id"]
    if not _consented(runtime, user_id):
        return {"outcome": "no_consent"}
    with account.open_store(runtime.context.store_path) as conn:
        try:
            diary.check_profile_saved(conn, user_id)
        except diary.DiaryError:
            return {"outcome": "profile_first"}
        except NotFound:
            return {"outcome": "not_found"}
    if not runtime.context.file:
        return {"outcome": "nothing"}
    text = media.read_media(
        runtime.context.media_model(),
        state["kind"],
        runtime.context.media_prompt.text,
        runtime.context.file,
    )
    if media.is_nothing(text):
        return {"outcome": "nothing"}
    return {"text": text}


def check(state: MediaState, runtime: Runtime[MediaContext]) -> dict[str, Any]:
    """Run the input guard and the domain guardrails on the model's text; a refusal ends the run."""
    checked = guard.check_text(state["text"] or "", max_chars=config.MEDIA_TEXT_MAX_CHARS)
    if checked.allowed:
        return {"text": checked.text}
    # Refused (an injection, or a domain guardrail such as an injury): never sent to a model.
    logger.info(
        "guard_rejected",
        extra={"turn_id": runtime.context.turn_id, "reason": checked.reason, "code": checked.code},
    )
    return {"text": None, "refused": 1, "outcome": "refused"}


def extract(state: MediaState, runtime: Runtime[MediaContext]) -> dict[str, Any]:
    """Check consent (c) again, send the passed text to the draft model and make the cards."""
    if not _consented(runtime, state["user_id"]):
        # Withdrawn (or a new text) since the press: nothing more reaches a model.
        return {"outcome": "no_consent", "text": None}
    structured = runtime.context.chat_model().with_structured_output(
        drafting.DraftEntries, method="json_schema", include_raw=True
    )
    with llm.mapped_errors():
        reply = structured.invoke(
            drafting.build_messages(runtime.context.draft_prompt.text, state["text"])
        )
    if not isinstance(reply, Mapping):
        raise llm.InvalidReplyError(diagnostic="media draft reply off the schema")
    parsed = reply.get("parsed")
    if reply.get("parsing_error") is not None or not isinstance(parsed, drafting.DraftEntries):
        raise llm.InvalidReplyError(diagnostic="media draft reply off the schema")
    cards, dropped = drafting.cards_from(
        parsed, date.fromisoformat(state["day"]), runtime.context.food_table
    )
    update: dict[str, Any] = {"cards": cards, "cards_found": len(cards), "dropped": dropped}
    if not cards:
        update.update(outcome="nothing", text=None)
    return update


def decide(state: MediaState) -> dict[str, Any]:
    """Pause for the gymer's decision on every card (approve, edit or reject)."""
    answer = interrupt(
        {
            "kind": state["kind"],
            "text": state.get("text"),
            "cards": state["cards"],
            "error": state.get("error"),
        }
    )
    return {"decision": answer if isinstance(answer, Mapping) else {}}


def save(state: MediaState, runtime: Runtime[MediaContext]) -> dict[str, Any]:
    """Log the approved entries in one step; a decision the checks refuse asks again."""
    decisions = (state.get("decision") or {}).get("decisions")
    try:
        foods, weights, workouts = drafting.decided_entries(
            state["cards"], decisions, _today(runtime.context), runtime.context.food_table
        )
        with account.open_store(runtime.context.store_path) as conn:
            logged = drafts.save_entries(
                conn, state["user_id"], foods=foods, weights=weights, workouts=workouts
            )
    except (drafting.DraftError, diary.DiaryError) as exc:
        return {"error": exc.code, "decision": None}
    except values.StoreValueError:
        # A value the store's own checks refuse (a row the diary's checks let through).
        return {"error": "drafts.entry_invalid", "decision": None}
    except NotFound:
        return {"outcome": "not_found", "text": None, "cards": [], "decision": None}
    return {
        "text": None,
        "cards": [],
        "decision": None,
        "error": None,
        "logged": logged,
        "outcome": "done",
    }


def after_read(state: MediaState) -> str:
    """Check the model's text, or end."""
    return END if state.get("outcome") else "check"


def after_check(state: MediaState) -> str:
    """Draft from the text the guard passed, or end."""
    return END if state.get("outcome") else "extract"


def after_extract(state: MediaState) -> str:
    """Pause on the cards, or end."""
    return END if state.get("outcome") else "decide"


def after_save(state: MediaState) -> str:
    """Ask again after a decision the checks refused, else end."""
    return "decide" if state.get("error") and not state.get("outcome") else END


def _builder() -> StateGraph:
    """Return the workflow's graph before it is compiled."""
    builder = StateGraph(MediaState, context_schema=MediaContext)
    builder.add_node("read", read)
    builder.add_node("check", check)
    builder.add_node("extract", extract)
    builder.add_node("decide", decide)
    builder.add_node("save", save)
    builder.add_edge(START, "read")
    builder.add_conditional_edges("read", after_read, ["check", END])
    builder.add_conditional_edges("check", after_check, ["extract", END])
    builder.add_conditional_edges("extract", after_extract, ["decide", END])
    builder.add_edge("decide", "save")
    builder.add_conditional_edges("save", after_save, ["decide", END])
    return builder


def mermaid() -> str:
    """Return the workflow's diagram in Mermaid, for the docs."""
    return _builder().compile().get_graph().draw_mermaid()


def _counts(found: Mapping) -> dict[str, int]:
    """Return a run's counts under their log names."""
    return {
        "refused": found.get("refused", 0),
        "cards": found.get("cards_found", 0),
        "dropped": found.get("dropped", 0),
        "logged": found.get("logged", 0),
    }


class MediaDrafter:
    """One browser session's runs from a photo or voice note: its own InMemorySaver and graph."""

    def __init__(self) -> None:
        """Start with no run; each press of the button starts a new thread."""
        self.checkpointer = InMemorySaver()
        self.graph = _builder().compile(checkpointer=self.checkpointer)
        self.thread_id: str | None = None
        # The instructions the run started with: a decision resumes with the same ones.
        self.media_prompt: chat.Prompt | None = None
        self.draft_prompt: chat.Prompt | None = None

    def _config(self) -> RunnableConfig:
        """Return the run's config: its thread and the step limit (no trace metadata: untraced)."""
        return {
            "configurable": {"thread_id": self.thread_id},
            "recursion_limit": config.MEDIA_MAX_STEPS,
        }

    def _result(self) -> RunResult:
        """Return where the run stands: waiting on its cards, or how it ended."""
        snapshot = self.graph.get_state(self._config())
        found = snapshot.values
        for paused in snapshot.interrupts:
            waiting = paused.value
            return RunResult(
                outcome="pending",
                kind=waiting["kind"],
                text=waiting.get("text"),
                cards=tuple(waiting["cards"]),
                error=waiting.get("error"),
                counts=_counts(found),
            )
        return RunResult(
            outcome=found.get("outcome") or "done",
            kind=found.get("kind"),
            logged=found.get("logged", 0),
            counts=_counts(found),
        )

    def _run(self, update: object, context: MediaContext, step: str) -> RunResult:
        """Invoke the graph untraced; a model or store error ends the run with nothing logged."""
        turn_id = str(uuid.uuid4())
        context = dataclasses.replace(context, turn_id=turn_id)
        if isinstance(update, Mapping):
            kind = update.get("kind")
        else:
            kind = self.graph.get_state(self._config()).values.get("kind")
        try:
            with tracing.untraced():
                self.graph.invoke(update, self._config(), context=context)
        except (*_RUN_ERRORS, account.StoreUnavailable) as exc:
            self._forget()
            if isinstance(exc, account.StoreUnavailable):
                result = RunResult(outcome="error", error_code="account.store_unavailable")
            else:
                result = _failed(exc, turn_id)
            _log(result, turn_id, kind, step, self)
            return result
        result = self._result()
        _log(result, turn_id, kind, step, self)
        if result.outcome != "pending":
            self._forget()
        return result

    def _forget(self) -> None:
        """Delete the current thread's checkpoints (the model's text among them) from memory."""
        if self.thread_id is not None:
            self.checkpointer.delete_thread(self.thread_id)
        self.thread_id = None

    def start(self, context: MediaContext, user_id: str, kind: media.Kind, day: date) -> RunResult:
        """Start a run on the gymer's press: up to the cards, or its end."""
        self._forget()
        self.thread_id = str(uuid.uuid4())
        self.media_prompt = context.media_prompt
        self.draft_prompt = context.draft_prompt
        start: MediaState = {"user_id": user_id, "kind": kind, "day": day.isoformat()}
        return self._run(start, context, "run")

    def pending(self) -> RunResult | None:
        """Return the cards the run waits on, or None when no run waits."""
        if self.thread_id is None:
            return None
        result = self._result()
        return result if result.outcome == "pending" else None

    def decide(self, context: MediaContext, decisions: Sequence[Mapping]) -> RunResult:
        """Resume the waiting run with the gymer's decision on every card."""
        if self.pending() is None:
            return RunResult(outcome="done")
        if self.media_prompt is not None and self.draft_prompt is not None:
            context = dataclasses.replace(
                context, media_prompt=self.media_prompt, draft_prompt=self.draft_prompt
            )
        # A decision sends no file: the first call is behind it.
        context = dataclasses.replace(context, file=b"")
        return self._run(Command(resume={"decisions": list(decisions)}), context, "decision")

    def drop(self) -> None:
        """Forget the run and its drafts at once (e.g. consent (c) withdrawn)."""
        self._forget()


def _failed(exc: Exception, turn_id: str) -> RunResult:
    """Log a failed run by its codes only and return the error outcome with the message's key."""
    code = getattr(exc, "code", None) or _SETUP_CODES.get(type(exc), "llm.error")
    logger.warning(
        "llm_error",
        extra={
            "turn_id": turn_id,
            "kind": "media_draft",
            "code": code,
            "status_code": getattr(exc, "status_code", None),
            "diagnostic": getattr(exc, "diagnostic", None) or llm.error_diagnostic(exc),
        },
    )
    return RunResult(outcome="error", error_code=code)


def _log(result: RunResult, turn_id: str, kind: object, step: str, drafter: MediaDrafter) -> None:
    """Write one line per run or decision: its ID, kind, outcome and counts, never a value."""
    logger.info(
        "media_draft",
        extra={
            "turn_id": turn_id,
            "kind": f"{kind}_{step}" if kind in ("photo", "voice") else step,
            "code": result.outcome,
            **result.counts,
            "prompt_media": drafter.media_prompt.version if drafter.media_prompt else None,
            tracing.PROMPT_DRAFTS_KEY: drafter.draft_prompt.version
            if drafter.draft_prompt
            else None,
        },
    )
