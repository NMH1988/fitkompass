"""Drafts of log entries from a gymer's own messages, as a fixed LangGraph workflow (T11.5, D26).

load -> next (guard) -> extract -> decide (interrupt) -> save -> next ... Each step is fixed; the
model only reads one message and returns its entries; the matching, the numbers and the checks are
code (`src/drafting.py`), and the gymer decides each card before anything is logged: the course's
human-in-the-loop pattern (D17).

- **load** runs only when the gymer pressed the button (never on its own): it checks consent (a)
  to the text the gymer reads now and a saved profile, then reads the gymer's own undrafted
  messages of their active thread from the diary's window, oldest first, at most
  `config.DRAFT_MAX_MESSAGES_PER_RUN` (never the coach's messages).
- **next** takes the next message and runs the input guard and the domain guardrails on it
  (`guard.check_text()`, no model call); a refused message is marked finished in the store, so it
  never reaches a model, and the run goes on with the next one.
- **extract** checks consent (a) again right before the model call, sends the one message (the
  client's text as data, no name) and turns the reply into cards in code; a message with no card
  is marked finished.
- **decide** pauses with `interrupt()` on the message's cards; the gymer's approve, edit or reject
  of every card resumes it with `Command(resume=...)`, and **save** logs the approved entries and
  marks the message in one store transaction (`drafts.save_step()`), or says it was already
  handled (another tab); a decision that fails the diary's checks pauses again with its code.

The run is checkpointed in the session's memory only (`InMemorySaver`), as a draft is not data
until it is approved: a session that ends before a message's step is saved logs nothing, and the
message is drafted again on a later press. A model error ends the run with nothing logged; the
error is logged as a diagnostic and the page shows a fixed message.
"""

import dataclasses
import logging
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Literal, TypedDict
from zoneinfo import ZoneInfo

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

from src import account, chat, config, diary, drafting, guard, llm, metrics, tracing
from src.store import ai_consents, drafts, values
from src.store.access import NotFound
from src.tools.food import Food

logger = logging.getLogger(__name__)

# How a run ended, or that it waits for the gymer; the page shows a fixed text for each.
Outcome = Literal["pending", "done", "nothing", "no_consent", "profile_first", "not_found", "error"]
_RUN_ERRORS = (llm.LLMError, config.MissingAPIKeyError)
_SETUP_CODES: dict[type, str] = {
    config.SecretsFileError: "key.secrets_file",
    config.MissingAPIKeyError: "key.missing",
}


class DraftState(TypedDict, total=False):
    """A run's state, kept in the session's memory: IDs, the queue, the current cards, counts."""

    user_id: str
    relationship_id: int
    # The messages still to draft ({id, text, created_at}). A message's text leaves the current
    # state once its reply is read; the thread's earlier checkpoints keep it until Drafter forgets
    # the thread (the run's end, a withdrawal).
    queue: list[dict]
    message: dict | None
    cards: list[dict]
    decision: dict | None
    # The i18n key of why the last decision could not be logged; the card asks again.
    error: str | None
    # The outcome of the gymer's last step, set by save: logged now ("saved") or already handled
    # ("already"), and how many entries that step logged; cleared at each new decision.
    last: str | None
    step_logged: int
    messages_read: int
    # How many messages the run took at the press, and how many it passed over with no card
    # (no entry in them, or deleted or finished meanwhile); the guard's refusals are counted
    # apart.
    total: int
    skipped: int
    refused: int
    cards_found: int
    dropped: int
    logged: int
    outcome: Outcome


@dataclass(frozen=True)
class DraftContext:
    """What the nodes use but never keep in state: the store file, the model, prompt and checks."""

    store_path: Path
    # The owner's instruction (O19) as read once for this run; its version goes on the trace.
    prompt: chat.Prompt
    # The version of consent (a)'s text the gymer reads now; a consent to another is none.
    consent_version: str = field(default_factory=drafting.consent_version)
    # Called only right before a model call, after the guard and the consent check passed.
    chat_model: Callable[[], BaseChatModel] = field(default=lambda: drafting.build_model())
    # The USDA table; None reads the committed one. Tests pass their own.
    food_table: Sequence[Food] | None = None
    # The day the run counts as today (Europe/Berlin); None for the real day. Tests set it.
    today: date | None = None
    # The ID of the run or decision in progress, for its log lines; set by Drafter for each one.
    turn_id: str = ""


@dataclass(frozen=True)
class RunResult:
    """How a run or decision ended (or waits), the cards to show while it waits, and its counts."""

    outcome: Outcome
    message_id: int | None = None
    message_day: str | None = None
    cards: tuple[dict, ...] = ()
    error: str | None = None
    # The last step's outcome in this run or decision ("saved" or "already") and its entries.
    last: str | None = None
    step_logged: int = 0
    # Where a waiting run stands: the message shown is number `position` of `total`, and
    # `skipped` messages were passed over before it (refused by the guard, with no entry, or
    # deleted or finished elsewhere meanwhile).
    position: int = 0
    total: int = 0
    skipped: int = 0
    counts: Mapping[str, int] = field(default_factory=dict)
    error_code: str | None = None


def _today(context: DraftContext) -> date:
    """Return the run's today in Europe/Berlin."""
    return context.today or metrics.berlin_day()


def _since(today: date) -> datetime:
    """Return the start of the diary's window as a UTC time: messages before it are not read."""
    first = today - timedelta(days=config.DIARY_MAX_DAYS_BACK)
    return datetime.combine(first, time(0), tzinfo=ZoneInfo(config.TIME_ZONE)).astimezone(UTC)


def _consented(runtime: Runtime[DraftContext], user_id: str) -> bool:
    """Return whether the gymer's consent (a) to the current text holds, read from the store now."""
    with account.open_store(runtime.context.store_path) as conn:
        return ai_consents.is_given(
            conn, user_id, drafting.PURPOSE, runtime.context.consent_version
        )


def load(state: DraftState, runtime: Runtime[DraftContext]) -> dict[str, Any]:
    """Check consent (a) and the profile, then read the gymer's own undrafted messages."""
    user_id = state["user_id"]
    if not _consented(runtime, user_id):
        return {"outcome": "no_consent"}
    today = _today(runtime.context)
    with account.open_store(runtime.context.store_path) as conn:
        try:
            diary.check_profile_saved(conn, user_id)
        except diary.DiaryError:
            return {"outcome": "profile_first"}
        except NotFound:
            return {"outcome": "not_found"}
        try:
            queue = drafts.undrafted_messages(
                conn,
                user_id,
                state["relationship_id"],
                since=_since(today),
                limit=config.DRAFT_MAX_MESSAGES_PER_RUN,
            )
        except NotFound:
            return {"outcome": "not_found"}
    if not queue:
        return {"outcome": "nothing", "queue": []}
    return {
        "queue": queue,
        "total": len(queue),
        "skipped": 0,
        "messages_read": 0,
        "refused": 0,
        "cards_found": 0,
        "dropped": 0,
        "logged": 0,
    }


def _finish(runtime: Runtime[DraftContext], user_id: str, message: Mapping) -> None:
    """Mark a message the run has finished with (no card, or refused by the guard)."""
    with account.open_store(runtime.context.store_path) as conn:
        try:
            drafts.mark_finished(conn, user_id, message["id"], message["created_at"])
        except NotFound:
            pass  # the message was deleted meanwhile (with either side's data): nothing to mark


def next_message(state: DraftState, runtime: Runtime[DraftContext]) -> dict[str, Any]:
    """Take the next message the guard passes; mark the refused ones; end when none is left."""
    queue = list(state.get("queue", ()))
    refused = state.get("refused", 0)
    read = state.get("messages_read", 0)
    while queue:
        message = queue.pop(0)
        read += 1
        checked = guard.check_text(message["text"], max_chars=config.MESSAGE_MAX_CHARS)
        if checked.allowed:
            current = {"id": message["id"], "created_at": message["created_at"]}
            current["text"] = checked.text
            return {"queue": queue, "message": current, "messages_read": read, "refused": refused}
        # Refused (an injection, or a domain guardrail such as an injury): never sent to a model.
        refused += 1
        logger.info(
            "guard_rejected",
            extra={
                "turn_id": runtime.context.turn_id,
                "reason": checked.reason,
                "code": checked.code,
            },
        )
        _finish(runtime, state["user_id"], message)
    return {
        "queue": [],
        "message": None,
        "messages_read": read,
        "refused": refused,
        "outcome": "done",
    }


def extract(state: DraftState, runtime: Runtime[DraftContext]) -> dict[str, Any]:
    """Check consent (a) again, send the one message to the model and turn the reply into cards."""
    message = state["message"]
    if not _consented(runtime, state["user_id"]):
        # Withdrawn (or a new text) since the press: nothing more reaches a model.
        return {"outcome": "no_consent", "message": None, "queue": []}
    with account.open_store(runtime.context.store_path) as conn:
        still_open = drafts.is_open_thread(conn, state["user_id"], state["relationship_id"])
        still_there = still_open and drafts.is_still_undrafted(
            conn, state["user_id"], state["relationship_id"], message["id"], message["created_at"]
        )
    if not still_open:
        # The relationship ended while the run waited: none of its messages reaches a model.
        return {"outcome": "not_found", "message": None, "queue": []}
    if not still_there:
        # Deleted meanwhile, or finished in another tab: not sent; the run goes on with the next.
        return {"message": None, "skipped": state.get("skipped", 0) + 1}
    model = runtime.context.chat_model()
    structured = model.with_structured_output(
        drafting.DraftEntries, method="json_schema", include_raw=True
    )
    with llm.mapped_errors():
        reply = structured.invoke(
            drafting.build_messages(runtime.context.prompt.text, message["text"])
        )
    if not isinstance(reply, Mapping):
        raise llm.InvalidReplyError(diagnostic="draft reply off the schema")
    parsed = reply.get("parsed")
    if reply.get("parsing_error") is not None or not isinstance(parsed, drafting.DraftEntries):
        raise llm.InvalidReplyError(diagnostic="draft reply off the schema")
    day = drafting.message_day(message["created_at"])
    cards, dropped = drafting.cards_from(parsed, day, runtime.context.food_table)
    kept = {"id": message["id"], "created_at": message["created_at"]}  # the text leaves the state
    update = {
        "message": kept,
        "cards": cards,
        "error": None,
        "cards_found": state.get("cards_found", 0) + len(cards),
        "dropped": state.get("dropped", 0) + dropped,
    }
    if not cards:
        _finish(runtime, state["user_id"], message)
        update["message"] = None
        update["skipped"] = state.get("skipped", 0) + 1
    return update


def decide(state: DraftState) -> dict[str, Any]:
    """Pause for the gymer's decision on every card of the message (approve, edit or reject)."""
    message = state["message"]
    answer = interrupt(
        {
            "message_id": message["id"],
            "message_day": drafting.message_day(message["created_at"]).isoformat(),
            "cards": state["cards"],
            "error": state.get("error"),
        }
    )
    # A new decision: the earlier step's outcome is not this one's.
    return {
        "decision": answer if isinstance(answer, Mapping) else {},
        "last": None,
        "step_logged": 0,
    }


def save(state: DraftState, runtime: Runtime[DraftContext]) -> dict[str, Any]:
    """Log the message's approved entries and mark it in one step; a bad decision asks again."""
    decisions = (state.get("decision") or {}).get("decisions")
    try:
        foods, weights, workouts = drafting.decided_entries(
            state["cards"], decisions, _today(runtime.context), runtime.context.food_table
        )
        with account.open_store(runtime.context.store_path) as conn:
            saved = drafts.save_step(
                conn,
                state["user_id"],
                state["message"]["id"],
                foods=foods,
                weights=weights,
                workouts=workouts,
                created_at=state["message"]["created_at"],
            )
    except (drafting.DraftError, diary.DiaryError) as exc:
        return {"error": exc.code, "decision": None}
    except values.StoreValueError:
        # A value the store's own checks refuse (a row the diary's checks let through).
        return {"error": "drafts.entry_invalid", "decision": None}
    except NotFound:
        return {"outcome": "not_found", "message": None, "cards": [], "decision": None}
    logged = len(foods) + len(weights) + len(workouts) if saved else 0
    return {
        "message": None,
        "cards": [],
        "decision": None,
        "error": None,
        "last": "saved" if saved else "already",
        "step_logged": logged,
        "logged": state.get("logged", 0) + logged,
    }


def after_load(state: DraftState) -> str:
    """Go on to the first message, or end."""
    return END if state.get("outcome") else "next"


def after_next(state: DraftState) -> str:
    """Draft the message the guard passed, or end."""
    return "extract" if state.get("message") else END


def after_extract(state: DraftState) -> str:
    """Pause on the cards, go on with the next message, or end."""
    if state.get("outcome"):
        return END
    return "decide" if state.get("message") else "next"


def after_save(state: DraftState) -> str:
    """Ask again after a bad decision, end after a refusal, else go on with the next message."""
    if state.get("error"):
        return "decide"
    return END if state.get("outcome") else "next"


def _builder() -> StateGraph:
    """Return the workflow's graph before it is compiled."""
    builder = StateGraph(DraftState, context_schema=DraftContext)
    builder.add_node("load", load)
    builder.add_node("next", next_message)
    builder.add_node("extract", extract)
    builder.add_node("decide", decide)
    builder.add_node("save", save)
    builder.add_edge(START, "load")
    builder.add_conditional_edges("load", after_load, ["next", END])
    builder.add_conditional_edges("next", after_next, ["extract", END])
    builder.add_conditional_edges("extract", after_extract, ["decide", "next", END])
    builder.add_edge("decide", "save")
    builder.add_conditional_edges("save", after_save, ["decide", "next", END])
    return builder


def mermaid() -> str:
    """Return the workflow's diagram in Mermaid, for the docs."""
    return _builder().compile().get_graph().draw_mermaid()


def _counts(values: Mapping) -> dict[str, int]:
    """Return a run's counts under their log names."""
    return {
        "messages_read": values.get("messages_read", 0),
        "refused": values.get("refused", 0),
        "cards": values.get("cards_found", 0),
        "dropped": values.get("dropped", 0),
        "logged": values.get("logged", 0),
    }


class Drafter:
    """One browser session's drafting runs: its own InMemorySaver, graph and current thread."""

    def __init__(self) -> None:
        """Start with no run; each press of the button starts a new thread."""
        self.checkpointer = InMemorySaver()
        self.graph = _builder().compile(checkpointer=self.checkpointer)
        self.thread_id: str | None = None
        # The run's relationship and the instruction it started with: a decision resumes with the
        # same instruction, so every call of a run sends the text its version names.
        self.relationship_id: int | None = None
        self.prompt: chat.Prompt | None = None

    def _config(self, turn_id: str) -> RunnableConfig:
        """Return the run's config: its thread, the turn_id and prompt version, the step limit."""
        prompts = {tracing.PROMPT_DRAFTS_KEY: self.prompt.version} if self.prompt else {}
        return {
            "configurable": {"thread_id": self.thread_id},
            "metadata": tracing.run_metadata(turn_id, prompts),
            "recursion_limit": config.DRAFT_MAX_STEPS,
        }

    def _result(self, turn_id: str) -> RunResult:
        """Return where the run stands: waiting on a message's cards, or how it ended."""
        snapshot = self.graph.get_state(self._config(turn_id))
        values = snapshot.values
        for paused in snapshot.interrupts:
            found = paused.value
            return RunResult(
                outcome="pending",
                message_id=found["message_id"],
                message_day=found["message_day"],
                cards=tuple(found["cards"]),
                error=found.get("error"),
                last=values.get("last"),
                step_logged=values.get("step_logged", 0),
                position=values.get("messages_read", 0),
                total=values.get("total", 0),
                skipped=values.get("skipped", 0) + values.get("refused", 0),
                counts=_counts(values),
            )
        return RunResult(
            outcome=values.get("outcome") or "done",
            last=values.get("last"),
            step_logged=values.get("step_logged", 0),
            counts=_counts(values),
        )

    def _run(self, update: object, context: DraftContext, kind: str) -> RunResult:
        """Invoke the graph with a start or a resume; a model error ends the run with no entry."""
        turn_id = str(uuid.uuid4())
        context = dataclasses.replace(context, turn_id=turn_id)
        try:
            self.graph.invoke(update, self._config(turn_id), context=context)
        except (*_RUN_ERRORS, account.StoreUnavailable) as exc:
            # A step saved before the error in this resume is still reported (its checkpoint was
            # written when save finished), so the gymer knows it was logged.
            done = self.graph.get_state(self._config(turn_id)).values
            self._forget()
            if isinstance(exc, account.StoreUnavailable):
                result = RunResult(outcome="error", error_code="account.store_unavailable")
            else:
                result = _failed(exc, turn_id)
            return dataclasses.replace(
                result, last=done.get("last"), step_logged=done.get("step_logged", 0)
            )
        result = self._result(turn_id)
        if result.outcome != "pending":
            self._forget()
        _log(result, turn_id, kind, self.prompt.version if self.prompt else None)
        return result

    def _forget(self) -> None:
        """Delete the current thread's checkpoints (the messages' text among them) from memory."""
        if self.thread_id is not None:
            self.checkpointer.delete_thread(self.thread_id)
        self.thread_id = None
        self.relationship_id = None

    def start(self, context: DraftContext, user_id: str, relationship_id: int) -> RunResult:
        """Start a run on the gymer's press: up to the first message's cards, or its end."""
        self._forget()
        self.thread_id = str(uuid.uuid4())
        self.relationship_id = relationship_id
        self.prompt = context.prompt
        start: DraftState = {"user_id": user_id, "relationship_id": relationship_id}
        return self._run(start, context, "run")

    def pending(self) -> RunResult | None:
        """Return the cards the run waits on, or None when no run waits."""
        if self.thread_id is None:
            return None
        result = self._result("")
        return result if result.outcome == "pending" else None

    def decide(self, context: DraftContext, decisions: Sequence[Mapping]) -> RunResult:
        """Resume the waiting run with the gymer's decision on every card of its message."""
        if self.pending() is None:
            return RunResult(outcome="done")
        if self.prompt is not None:
            context = dataclasses.replace(context, prompt=self.prompt)
        resume = Command(resume={"decisions": list(decisions)})
        return self._run(resume, context, "decision")

    def drop(self) -> None:
        """Forget the run and its drafts at once (no consent, or its thread no longer active)."""
        self._forget()


def _failed(exc: Exception, turn_id: str) -> RunResult:
    """Log a failed run by its codes only and return the error outcome with the message's key."""
    code = getattr(exc, "code", None) or _SETUP_CODES.get(type(exc), "llm.error")
    logger.warning(
        "llm_error",
        extra={
            "turn_id": turn_id,
            "kind": "draft_entries",
            "code": code,
            "status_code": getattr(exc, "status_code", None),
            "diagnostic": getattr(exc, "diagnostic", None) or llm.error_diagnostic(exc),
        },
    )
    return RunResult(outcome="error", error_code=code)


def _log(result: RunResult, turn_id: str, kind: str, prompt_version: str | None) -> None:
    """Write one line per run or decision: its ID, outcome and counts, never a value."""
    logger.info(
        "draft_entries",
        extra={
            "turn_id": turn_id,
            "kind": kind,
            "code": result.outcome,
            **result.counts,
            tracing.PROMPT_DRAFTS_KEY: prompt_version,
        },
    )
