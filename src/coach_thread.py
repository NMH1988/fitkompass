"""Consent (b) for the coach's AI and the client's thread (T11.6a, D30): its texts and versions.

Consent (b) has a switch per use (`src/store/ai_consents.py`). A use's text is the common part
(the purpose, the coach, OpenRouter and the provider, what is never sent) followed by the use's own
part; its version is worked out from both, in both languages, so a change to either asks the
gymer again for that use alone, and a use a later ticket adds has a text and a version of its
own, leaving the uses already set as they are. The coach's display name is shown in the text but
is not part of the version: it is put in as a fixed placeholder when the version is worked out,
so a coach renaming themselves asks nobody again.

This module imports no streamlit.
"""

from typing import Any

from src import config, i18n, llm
from src.store import ai_consents

PURPOSE = ai_consents.WITH_USES
# The uses built so far, each with its text's key; T11.6b adds `reply`, T11.14 `review`, T11.15
# `foods`.
USE_TEXT_KEYS: dict[str, str] = {"chat": "coach_ai.use_chat"}
INTRO_KEY = "coach_ai.consent_intro"
# What stands for the coach's name when a version is worked out.
_COACH_PLACEHOLDER = "{coach}"


def build_chat_model(*, api_key: str | None = None, http_client: Any = None):
    """Build a coach's chat model: the answer model, its cap, and the providers (b) names."""
    # The one place it is built, so the provider pin that keeps consent (b)'s text true cannot be
    # left out: a coach's chat may send a client's messages through get_client_thread.
    return llm.build_chat_model(
        config.DEFAULT_ANSWER_MODEL,
        config.DEFAULT_MAX_TOKENS,
        providers=config.COACH_CHAT_PROVIDERS,
        api_key=api_key,
        http_client=http_client,
    )


def model_provider() -> str:
    """Return the name of the provider a coach's chat model is pinned to, as the text shows it."""
    names = {"openai": "OpenAI", "azure": "Microsoft Azure"}
    return " / ".join(names.get(slug, slug) for slug in config.COACH_CHAT_PROVIDERS)


def intro_text(lang: i18n.Language, coach: str) -> str:
    """Return consent (b)'s common part in a language, naming the coach and the provider."""
    return i18n.t(INTRO_KEY, lang, coach=coach, provider=model_provider())


def use_text(lang: i18n.Language, coach: str, use: str) -> str:
    """Return one use's own part of consent (b) in a language, naming the coach."""
    return i18n.t(USE_TEXT_KEYS[use], lang, coach=coach, count=config.THREAD_MESSAGES_TO_MODEL)


def use_version(use: str) -> str:
    """Return the version of a use's text: the common part and its own, in both languages."""
    parts = [
        intro_text(lang, _COACH_PLACEHOLDER) + "\n" + use_text(lang, _COACH_PLACEHOLDER, use)
        for lang in ("en", "de")
    ]
    # Imported here: src/chat.py imports the thread tool, which imports this module.
    from src.chat import prompt_version

    return prompt_version("\n".join(parts))
