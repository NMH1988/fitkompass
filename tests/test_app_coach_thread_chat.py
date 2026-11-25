"""UI tests for a client's thread in the coach's AI chat (T11.6a, AC-50).

A coach is signed in with one client whose consent (b) has its `chat` use on; a scripted model
reads the thread and answers. The page says, in code, how many messages the guards left out, and
says nothing when the client later switches the use off: the earlier answer stays on the coach's
screen and only leaves what the model receives.
"""

import re

import pytest
import streamlit as st
from langchain_core.messages import AIMessage
from streamlit.testing.v1 import AppTest

from src import coach_thread
from src.store import ai_consents, db, messages, users
from src.tools.client_thread import THREAD_TOOL
from src.tools.coach_clients import LIST_TOOL
from tests.fakes import ScriptedChatModel, tool_reply
from tests.test_app_account import USER_ID, signed_in, start, store_account, texts
from tests.test_app_chat import _use_model, fakes, index_path  # noqa: F401 (fixtures)

pytestmark = pytest.mark.usefixtures("no_env_key")

CLIENT = "gym-client-t116a"
CANARY = "CANARY-THREAD oats and eggs for breakfast all week"
INJURY = "CANARY-INJURY my knee is injured and swollen since Tuesday"


def _coach(monkeypatch, language: str = "en") -> tuple[AppTest, int]:
    """Sign in a coach with one client whose chat use is on and who wrote two messages."""
    store_account("coach", "Coach Sam")
    with db.connect() as conn:
        users.create_user(conn, CLIENT, "gymer", "Client Kim")
        relationship = users.start_relationship(conn, USER_ID, CLIENT)
        version = coach_thread.use_version("chat")
        ai_consents.give(conn, CLIENT, "coach_thread", version, relationship, "chat")
        messages.send_message(conn, CLIENT, relationship, CANARY)
        messages.send_message(conn, CLIENT, relationship, INJURY)
    return start(monkeypatch, user=signed_in(), language=language), relationship


def _ask(at: AppTest, question: str) -> AppTest:
    """Ask the chat a question and run the page."""
    return at.chat_input(key="chat_input").set_value(question).run(timeout=30)


def _thread_turn(monkeypatch, language: str = "en"):
    """Ask for a summary: the model lists the clients, reads client-1's thread and answers."""
    at, relationship = _coach(monkeypatch, language)
    model = ScriptedChatModel(
        replies=[
            tool_reply((LIST_TOOL, {})),
            tool_reply((THREAD_TOOL, {"client": "client-1"})),
            AIMessage(f"client-1 wrote: {CANARY}"),
        ],
        search_first=False,
    )
    _use_model(monkeypatch, model)
    return _ask(at, "Summarise client-1's messages this week."), model, relationship


@pytest.mark.parametrize(
    ("language", "line"),
    [
        ("en", "1 message(s) of this client's conversation were left out"),
        ("de", "1 Nachricht(en) des Gesprächs mit diesem Klienten hat die App"),
    ],
)
def test_the_page_says_how_many_messages_were_left_out(monkeypatch, language, line):
    """The injury never reaches the model; the page, not the model, says one was left out."""
    at, model, _ = _thread_turn(monkeypatch, language)
    warnings = "\n".join(str(item.value) for item in at.warning)
    assert line in warnings
    sent = "\n".join(str(item.content) for call in model.calls for item in call)
    assert CANARY in sent and "CANARY-INJURY" not in sent


def test_the_thread_shows_in_the_tool_results_as_plain_text(monkeypatch):
    """The coach sees the messages the AI read, as table cells, with no name of the client."""
    at, _, _ = _thread_turn(monkeypatch)
    [table] = [frame.value for frame in at.dataframe if "Message" in frame.value.columns]
    assert list(table["Message"]) == [CANARY]
    assert list(table["From"]) == ["Client"]


def test_after_the_client_switches_the_use_off_the_page_says_nothing(monkeypatch):
    """The earlier answer stays on screen; the next request holds no canary; no line about it."""
    at, _, relationship = _thread_turn(monkeypatch)
    before = texts(at)
    notes_before = _notes(at)
    with db.connect() as conn:
        ai_consents.withdraw(conn, CLIENT, "coach_thread", relationship, "chat")
    model = ScriptedChatModel(
        replies=[tool_reply((LIST_TOOL, {})), AIMessage("client-1 logged no day.")],
        search_first=False,
    )
    # The page caches the coach's model: cleared, so the second turn builds the new fake.
    st.cache_resource.clear()
    _use_model(monkeypatch, model)
    at = _ask(at, "Anything else?")
    assert model.calls, "the second turn never reached its model"
    assert not at.error
    sent = "\n".join(str(item.content) for call in model.calls for item in call)
    assert CANARY not in sent
    assert "logged no day." in texts(at)  # the answer, with the client's name in place
    after = texts(at)
    assert CANARY in before and CANARY in after  # the earlier answer is still shown
    new_notes = " ".join(_notes(at) - notes_before).casefold()
    for word in ("consent", "switched off", "removed", "withdrawn", "not available", "left out"):
        assert word not in new_notes


def _notes(at: AppTest) -> set[str]:
    """Return the page's notes: its warnings, infos, errors and captions."""
    items = [*at.warning, *at.info, *at.error, *at.caption]
    return {str(item.value) for item in items}


def test_the_left_out_line_shows_under_a_program_that_was_replaced(monkeypatch):
    """A program caught after a thread read still tells the coach a message was left out."""
    at, _ = _coach(monkeypatch)
    model = ScriptedChatModel(
        replies=[
            tool_reply((LIST_TOOL, {})),
            tool_reply((THREAD_TOOL, {"client": "client-1"})),
            AIMessage("Day 1: squats.\nDay 2: bench press."),
        ],
        search_first=False,
    )
    _use_model(monkeypatch, model)
    at = _ask(at, "Plan client-1's week from her messages.")
    warnings = "\n".join(str(item.value) for item in at.warning)
    assert "1 message(s) of this client's conversation were left out" in warnings


def _recording_builder(monkeypatch) -> list[dict]:
    """Make the app build a scripted model and record the arguments of every build."""
    from src import config, llm
    from tests.fakes import ScriptedTranslator

    builds: list[dict] = []
    model = ScriptedChatModel(
        replies=[tool_reply((LIST_TOOL, {})), AIMessage("client-1 logged no day.")],
        search_first=False,
    )

    def build(name: str = config.DEFAULT_ANSWER_MODEL, *args, **kwargs):
        """Record the build and return the fake for its model."""
        builds.append({"model": name, **kwargs})
        return ScriptedTranslator() if name == config.QUERY_TRANSLATION_MODEL else model

    st.cache_resource.clear()
    monkeypatch.setattr(llm, "build_chat_model", build)
    return builds


def _answer_builds(builds: list[dict]) -> list[dict]:
    """Return the builds of the answer model."""
    from src import config

    return [item for item in builds if item["model"] == config.DEFAULT_ANSWER_MODEL]


def test_a_coachs_chat_model_is_pinned_to_the_provider_consent_b_names(monkeypatch):
    """A coach's answer model is built with COACH_CHAT_PROVIDERS, the store readable or not."""
    from src import config
    from views import chat as chat_view

    at, _ = _coach(monkeypatch)
    builds = _recording_builder(monkeypatch)
    at = _ask(at, "Who logged least?")
    [built] = _answer_builds(builds)
    assert built["providers"] == config.COACH_CHAT_PROVIDERS
    # The coach's memory cannot be read: still the coach's pinned model.
    monkeypatch.setattr(chat_view, "coach_memory", lambda: None)
    builds = _recording_builder(monkeypatch)
    _ask(at, "And now?")
    [built] = _answer_builds(builds)
    assert built["providers"] == config.COACH_CHAT_PROVIDERS


def test_a_guests_chat_model_is_not_pinned(monkeypatch):
    """A guest's answer model is built without providers."""
    from tests.test_app_chat import _start

    builds = _recording_builder(monkeypatch)
    _ask(_start(), "How much protein after training?")
    assert _answer_builds(builds)
    assert all("providers" not in item for item in _answer_builds(builds))


@pytest.mark.parametrize(
    "link",
    [
        "[the full report](https://attacker.example/r?w=87.3)",
        "see https://attacker.example/r?w=87.3",
        "see www.attacker.example",
        "mail coach@attacker.example",
        "![x](https://attacker.example/p.png)",
        "see [the report][r]\n\n[r]: https://attacker.example/r?w=87.3",
        "see $\\href{https://attacker.example/r}{report}$",
        "see [a](https://attacker.example/a(b)c)",
        "see <https://attacker.example>",
        "see https&#58;//attacker.example/r?w=87.3",
        "see www&period;attacker.example/r",
        "mail x&#64;attacker.example",
        "mail x&commat;attacker.example",
    ],
)
def test_a_link_in_a_coachs_answer_is_shown_as_text(monkeypatch, link):
    """No link, autolink or image in a coach's answer: a message could ask for one."""
    at, _ = _coach(monkeypatch)
    model = ScriptedChatModel(
        replies=[tool_reply((LIST_TOOL, {})), AIMessage(f"client-1 logged no day; {link}")],
        search_first=False,
    )
    _use_model(monkeypatch, model)
    at = _ask(at, "Who logged least?")
    shown = "\n".join(str(item.value) for item in at.markdown if "logged no day" in item.value)
    assert shown
    # An escaped bracket ("\](") is text; an unescaped "](" would open a link.
    assert re.search(r"(?<!\\)\]\(", shown) is None
    assert "https://" not in shown and "www." not in shown
    # A character reference is shown as text: its "&" escaped, so it decodes into nothing.
    assert re.search(r"(?<!\\)&", shown) is None
    assert "⁠@" in shown or "@" not in shown


def test_a_normal_coach_answer_keeps_names_citations_bold_and_dollars(monkeypatch):
    """Breaking links leaves the rest: the client's name, both citations, bold, a literal $."""
    at, _ = _coach(monkeypatch)
    answer = (
        "**client-1** logged no day [S1, S3]; protein timing matters [S1][S2]; it costs $5; "
        "that helps! [S3]"
    )
    model = ScriptedChatModel(
        replies=[tool_reply((LIST_TOOL, {})), AIMessage(answer)], search_first=False
    )
    _use_model(monkeypatch, model)
    at = _ask(at, "Who logged least?")
    [shown] = [str(item.value) for item in at.markdown if "logged no day" in item.value]
    assert "Client Kim" in shown and "client-1" not in shown
    assert r"\[S1, S3\]" in shown and r"\[S1\]\[S2\]" in shown
    assert "**" in shown and r"\$5" in shown
    assert r"helps! \[S3\]" in shown
