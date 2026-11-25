"""UI tests for consent (b), the coach's AI and the client's thread, on Messages (T11.6a)."""

import pytest
from streamlit.testing.v1 import AppTest

from src import coach_thread
from src.store import ai_consents, db, users
from tests.test_app_account import PROFILE, USER_ID, store_account, texts
from tests.test_app_messages import _pair, _run, _user

pytestmark = pytest.mark.usefixtures("no_env_key")

COACH = "coach-ola"


@pytest.fixture
def thread():
    """Store the signed-in gymer with a profile, their coach Ola and their thread."""
    store_account("gymer", "Mia", profile=PROFILE)
    _user(COACH, "coach", "Coach Ola")
    return _pair(COACH, USER_ID)


def _chat_on(thread_id: int) -> bool:
    """Return whether the gymer's `chat` use of consent (b) holds for its current text."""
    with db.connect() as conn:
        return ai_consents.is_given(
            conn, USER_ID, "coach_thread", coach_thread.use_version("chat"), thread_id, "chat"
        )


def _buttons(at: AppTest, label: str) -> list:
    """Return the page's buttons with this label."""
    return [item for item in at.button if item.label == label]


@pytest.mark.parametrize(
    ("language", "consent", "use", "switch_on", "switch_off"),
    [
        (
            "en",
            "Consent (Art. 9 GDPR) to AI help with your conversation with your coach, Coach Ola",
            "Coach Ola's AI chat reads your conversation.",
            "Switch on",
            "Switch off",
        ),
        (
            "de",
            "Einwilligung (Art. 9 DSGVO) in KI-Hilfe zu Ihrem Gespräch mit Ihrem Coach, Coach Ola",
            "Der KI-Chat von Coach Ola liest Ihr Gespräch.",
            "Einschalten",
            "Ausschalten",
        ),
    ],
)
def test_the_chat_use_names_the_coach_and_recipients_and_switches_in_one_click(
    monkeypatch, thread, language, consent, use, switch_on, switch_off
):
    """The text names the current coach, OpenRouter and OpenAI; one click on, one click off."""
    at = _run(monkeypatch, language=language)
    page = texts(at)
    assert consent in page and use in page
    assert "OpenRouter" in page and "OpenAI" in page
    assert not _chat_on(thread)
    _buttons(at, switch_on)[0].click()
    at.run(timeout=30)
    assert _chat_on(thread)
    assert _buttons(at, switch_off) and not _buttons(at, switch_on)
    _buttons(at, switch_off)[0].click()
    at.run(timeout=30)
    assert not _chat_on(thread)
    with db.connect() as conn:
        rows = conn.execute("SELECT use, withdrawn_at FROM ai_consents").fetchall()
    assert [(row[0], row[1] is not None) for row in rows] == [("chat", True)]


def test_consent_a_does_not_switch_on_the_chat_use(monkeypatch, thread):
    """Giving consent (a) for drafts leaves consent (b)'s chat use off."""
    at = _run(monkeypatch)
    [give] = _buttons(at, "Give this consent")
    give.click()
    at.run(timeout=30)
    assert not _chat_on(thread)


def test_a_chat_use_set_under_an_older_text_asks_again_and_can_be_switched_off(monkeypatch, thread):
    """An older text counts as off: the page says so and offers both switches."""
    with db.connect() as conn:
        ai_consents.give(conn, USER_ID, "coach_thread", "0123456789ab", thread, "chat")
    at = _run(monkeypatch)
    assert "The text of this use has changed" in texts(at)
    assert _buttons(at, "Switch on") and _buttons(at, "Switch off")
    _buttons(at, "Switch off")[0].click()
    at.run(timeout=30)
    with db.connect() as conn:
        assert ai_consents.current(conn, USER_ID, "coach_thread", thread, "chat") is None


def test_an_ended_thread_shows_no_consent_b(monkeypatch, thread):
    """Consent (b) ends with its relationship: an ended thread offers no switch."""
    with db.connect() as conn:
        users.end_relationship(conn, USER_ID, thread)
    at = _run(monkeypatch)
    page = texts(at)
    assert "AI help with your conversation" not in page
    assert not _buttons(at, "Switch on")


def test_the_coachs_name_is_shown_escaped(monkeypatch):
    """A coach's display name is plain text in the consent, never a link or Markdown."""
    store_account("gymer", "Mia", profile=PROFILE)
    _user(COACH, "coach", "[Ola](https://example.com) **bold**")
    _pair(COACH, USER_ID)
    at = _run(monkeypatch)
    markdown = "\n".join(str(item.value) for item in at.markdown)
    captions = "\n".join(str(item.value) for item in at.caption)
    assert "](https://example.com)" not in markdown + captions
    assert "\\[Ola\\]" in markdown + captions


@pytest.mark.parametrize(
    ("role", "language", "said"),
    [
        ("gymer", "en", "only if you switched that use on below"),
        ("gymer", "de", "nur wenn Sie diese Nutzung unten eingeschaltet haben"),
        ("coach", "en", "only if that client switched this use on"),
        ("coach", "de", "nur wenn dieser Klient diese Nutzung eingeschaltet hat"),
    ],
)
def test_the_intro_says_when_the_coachs_ai_reads_the_thread(monkeypatch, role, language, said):
    """Both roles' intro texts say the coach's AI reads the thread only with consent (b)."""
    store_account(role, "Mia", profile=PROFILE if role == "gymer" else None)
    at = _run(monkeypatch, language=language)
    page = " ".join(texts(at).split())
    assert said in page
    assert "never sent to the AI" not in page and "nie an die KI gesendet" not in page


@pytest.mark.parametrize(
    ("language", "sentences"),
    [
        (
            "en",
            (
                "which can be any week of your coaching with Coach Ola, also messages written "
                "before you switched this on",
                "The app does not store the answer, but Coach Ola can download their chat, with "
                "its answers, as a PDF.",
                "but they can miss some",
            ),
        ),
        (
            "de",
            (
                "die jede Woche Ihres Coachings mit Coach Ola sein kann, auch vor dem Einschalten "
                "geschriebene",
                "Die App speichert die Antwort nicht, aber Coach Ola kann den Chat mit seinen "
                "Antworten als PDF herunterladen.",
                "können aber einige übersehen",
            ),
        ),
    ],
)
def test_the_chat_use_says_any_week_the_pdf_and_that_the_checks_can_miss(
    monkeypatch, thread, language, sentences
):
    """The text says which weeks, that the coach can keep the answers, and the checks' limit."""
    at = _run(monkeypatch, language=language)
    page = " ".join(texts(at).split())
    for sentence in sentences:
        assert sentence in page
    assert "is not stored: it stays" not in page
