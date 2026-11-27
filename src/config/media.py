"""A photo or a voice note to draft log entries (T11.10, D29; `src/media.py`, its workflow)."""

from src.config.models import DEFAULT_ANSWER_MODEL, DEFAULT_MAX_TOKENS
from src.config.paths import PROJECT_ROOT

# The model that describes a photo: the draft model, which takes image input (on the allowlist,
# built by build_chat_model()), so consent (c) names no provider that consent (a) does not.
PHOTO_MODEL = DEFAULT_ANSWER_MODEL
# The model that transcribes a voice note: OpenAI's audio model, as gpt-5-mini takes no audio.
# OpenRouter serves it from OpenAI only (checked on 2026-11-25), and the course's key allows it.
VOICE_MODEL = "openai/gpt-audio-mini"
# The token cap of the first call (a description or a transcript of at most a minute of speech).
MEDIA_MAX_TOKENS = DEFAULT_MAX_TOKENS
# The only providers OpenRouter may route either model to, with no fallback: consent (c)'s text
# names them. The slug is OpenRouter's; `media.model_provider()` gives the name the text shows.
MEDIA_PROVIDERS: tuple[str, ...] = ("openai",)
# A photo as uploaded or taken: at most this size, of these types (the content is checked, not
# the name), and at most this many pixels once decoded (a small file can decode to a huge image).
PHOTO_MAX_MB = 5
PHOTO_MAX_BYTES = PHOTO_MAX_MB * 1024 * 1024
PHOTO_TYPES: tuple[str, ...] = ("jpg", "jpeg", "png")
PHOTO_MAX_PIXELS = 40_000_000
# The photo sent: re-encoded as a JPEG, its longer side at most this many pixels, at this quality.
# Enough to tell foods and portions apart, and a smaller request than a phone's full photo.
PHOTO_MAX_SIDE_PX = 1600
PHOTO_JPEG_QUALITY = 85
# A voice note, only from the browser's recording widget: at most this long, recorded at this
# rate (16 kHz mono is enough for speech), and a file no bigger than such a recording could be.
VOICE_MAX_SECONDS = 60
VOICE_SAMPLE_RATE = 16000
VOICE_MAX_BYTES = VOICE_MAX_SECONDS * 48000 * 2 + 4096
# The largest upload Streamlit's server takes, in MB: `server.maxUploadSize` in
# .streamlit/config.toml must say the same (tests/test_media.py), just above the photo and the voice
# limits, as these are the app's only uploads; the server refuses a bigger body while it streams.
UPLOAD_MAX_MB = 6
# The size up to which an upload part stays in memory while the server reads it. Starlette's default
# (1 MB) writes a bigger part to a temporary file on disk, so `media.keep_uploads_in_memory()` sets
# this, above the largest body the server takes (UPLOAD_MAX_MB and Streamlit's 1 MB allowance for
# the multipart framing).
UPLOAD_SPOOL_MAX_BYTES = (UPLOAD_MAX_MB + 2) * 1024 * 1024
# The longest description or transcript the input guard takes before the extraction.
MEDIA_TEXT_MAX_CHARS = 2000
# The owner's fixed instructions of the first call (owner task O19); the page says one is missing
# until its file has text.
PHOTO_PROMPT_PATH = PROJECT_ROOT / "src" / "prompts" / "media_photo_system.md"
VOICE_PROMPT_PATH = PROJECT_ROOT / "src" / "prompts" / "media_voice_system.md"
MEDIA_PROMPT_MISSING_MESSAGE = (
    "The instruction for reading a photo or a voice note (`src/prompts/media_photo_system.md` or "
    "`src/prompts/media_voice_system.md`) is missing or empty, so nothing can be drafted from it. "
    "Restore the file and try again."
)
# The step limit of one run: describe, check, extract, decide and save, decisions asked again.
MEDIA_MAX_STEPS = 20
