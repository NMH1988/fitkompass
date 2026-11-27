"""The coach's names in the session PDF's answers (views/export._named, T9.17 and T11.6a)."""

from src.chat import TurnResult
from views import export
from views.tables import WORD_JOINER

ANSWER = "client-1 wrote about breakfast."


def test_outside_a_coachs_chat_the_answer_stays_as_written():
    """A guest's or a gymer's turn (names None) and a coach with no client are left alone."""
    result = TurnResult("answer", ANSWER)
    assert export._named(result, None) is result
    assert export._named(result, {}) is result


def test_a_coachs_answer_shows_the_name_escaped_with_links_broken():
    """A reference becomes the client's name, one escaped line with its "www." broken."""
    result = TurnResult("answer", ANSWER)
    named = export._named(result, {"client-1": "www.kim.example"})
    assert "client-1" not in named.text
    assert "www" + WORD_JOINER + "." in named.text


def test_a_turn_that_is_not_an_answer_is_unchanged():
    """A refused or failed turn keeps its fixed text."""
    result = TurnResult("rejected", "client-1 rejected")
    assert export._named(result, {"client-1": "Kim"}) is result
