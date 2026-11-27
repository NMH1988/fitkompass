"""The coach's AI reads a client's thread (T11.6a, D30; `src/tools/client_thread.py`)."""

# The most messages of one week a thread result gives the model; the newest are kept.
THREAD_MESSAGES_TO_MODEL = 50
# The most characters of the messages' text, as escaped for the model, one thread result holds:
# a gymer writes the messages, so their size is a third party's; the newest are kept and the
# older ones counted. 50 messages of 300 characters fit, as do 15 full-length ones.
THREAD_CHARS_TO_MODEL = 15_000
# What the model reads when it calls remember_preference in a turn that holds a client's thread:
# a saved preference goes into every later chat, so it is never proposed from such a turn.
THREAD_NO_PREFERENCE_MESSAGE = (
    "Not proposed: no preference is proposed in a chat that holds a client's messages. The "
    "coach can ask to remember a preference in a new chat."
)
# At most this many get_client_thread calls run in one tool round; more are refused.
MAX_THREAD_CALLS_PER_ROUND = 1
TOO_MANY_THREAD_CALLS_MESSAGE = (
    "Not run: one client's messages per tool round. Ask for the next ones in the next round."
)
# The only providers OpenRouter may route a coach's chat model to, with no fallback: consent (b)'s
# text names them, as the chat may now send a client's messages (OpenRouter serves the answer model
# from OpenAI and from Azure). The slug is OpenRouter's; `coach_thread.model_provider()` gives the
# name the text shows. A guest's chat is not pinned.
COACH_CHAT_PROVIDERS: tuple[str, ...] = ("openai",)
# What the model reads when it calls the knowledge base search in a turn that holds a client's
# thread: the search sends its query to a query translation model and an embedding model that
# consent (b)'s text does not name, so it is off for the whole turn, whatever the client chose.
THREAD_SEARCH_OFF_MESSAGE = (
    "Not run: the knowledge base search is off in a chat that holds a client's messages. "
    "Answer from the tool results you have, without research sources, and say so; the coach "
    "can start a new chat to ask a research question."
)
# What the coach reads in place of "not covered" when a turn that holds a client's thread found
# no basis: the search was off, so the sources were not asked.
SEARCH_OFF_MESSAGE = (
    "The research search is off in a chat that holds a client's messages, so this question "
    "was not looked up in our sources, and no preference is saved. Start a new chat to ask a "
    "research question or to have me remember something."
)

# The one answer for every thread the tool may not read: an unknown reference, a former coach, no
# consent (b), its `chat` use off, a newer text not agreed to. It says nothing of which, so the chat
# never tells the coach what the client chose; it holds no message.
THREAD_NOT_AVAILABLE_MESSAGE = (
    "This client's messages are not available to this chat. Do not guess or describe what the "
    "client or the coach wrote; answer from the other tools' results, or say the messages are not "
    "available."
)
