"""A photo or a voice note, checked and cleaned in memory before the first model call (T11.10, D29).

A photo (JPEG or PNG, uploaded or taken with the camera) is checked by its content, not its name
(only Pillow's JPEG and PNG parsers read it):
at most `config.PHOTO_MAX_BYTES`, decoded by Pillow only if it holds at most
`config.PHOTO_MAX_PIXELS`, turned upright from its EXIF orientation, scaled down to
`config.PHOTO_MAX_SIDE_PX` and re-encoded as a new JPEG from its pixels alone, so no metadata
(location, device, time, a thumbnail, a colour profile) leaves the app. A voice note comes only from
the browser's recording widget: a PCM WAV of at most `config.VOICE_MAX_SECONDS`, re-written from its
samples alone with the standard library's `wave`, so no tag chunk leaves the app. Anything else is a
`MediaError` with a fixed code, raised before any model call. Nothing here touches the disk, and
`keep_uploads_in_memory()` keeps Streamlit's server from writing an upload to a temporary file.

The first model call sees only the owner's fixed instruction (O19) and the cleaned file, never a
profile, a message or a name. It is the one model call no guard checks first, as the guard reads
text: the whole file reaches OpenRouter and OpenAI, people or documents in it included, which
consent (c)'s text says (`.claude/rules/security-privacy.md`, "Guards"; `docs/SECURITY.md`).

The consent this flow needs is (c), `PURPOSE` (`docs/PRD.md`, "Consents"); its text's version is
worked out from the English and German texts, so a changed text asks again.
"""

import base64
import io
import wave
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.formparsers import MultiPartParser

from src import chat, config, i18n, llm

# Consent (c) of the PRD: drafts of log entries from the gymer's photos and voice notes.
PURPOSE = "media"
CONSENT_TEXT_KEY = "media.consent_text"
Kind = Literal["photo", "voice"]
# The only Pillow plugins tried on a photo's bytes, whatever its name says, so no other format's
# parser reads untrusted bytes.
_PHOTO_PLUGINS = ("JPEG", "PNG")
# What they may report: a JPEG that holds a second image (a large preview, an HDR gain map) opens as
# MPO; only its first image is re-encoded.
_PHOTO_FORMATS = frozenset({"JPEG", "MPO", "PNG"})
# The sample widths, in bytes, that wave writes back (it reads wider ones it cannot write).
_SAMPLE_WIDTHS = frozenset({1, 2, 3, 4})
# The fixed answer the owner's instructions give when there is nothing to describe or transcribe.
NOTHING_REPLY = "NONE"
# What a transparent part of a PNG becomes in the JPEG.
_BACKGROUND = (255, 255, 255)


class MediaError(ValueError):
    """A file that cannot be sent; `code` is the i18n key of its message (never a value)."""

    def __init__(self, code: str) -> None:
        """Keep the message's key."""
        super().__init__(code)
        self.code = code


def keep_uploads_in_memory() -> None:
    """Keep every upload part in memory while Streamlit's server reads it, never in a temp file."""
    # Streamlit 1.66 reads an upload with Starlette's request.form(), whose parser spools a part
    # over 1 MB into a temporary file on disk. Raised above the largest body the server takes
    # (config.UPLOAD_MAX_MB), no photo or recording is written there. A class attribute of the
    # library, set for the whole process (the uploads are only this flow's); idempotent.
    MultiPartParser.spool_max_size = max(
        MultiPartParser.spool_max_size, config.UPLOAD_SPOOL_MAX_BYTES
    )


def clean_photo(data: bytes) -> bytes:
    """Return a photo re-encoded as a JPEG of its pixels only; MediaError if it cannot be sent."""
    if not data:
        raise MediaError("media.photo_unreadable")
    if len(data) > config.PHOTO_MAX_BYTES:
        raise MediaError("media.photo_too_big")
    side = (config.PHOTO_MAX_SIDE_PX, config.PHOTO_MAX_SIDE_PX)
    try:
        with Image.open(io.BytesIO(data), formats=_PHOTO_PLUGINS) as image:
            if image.format not in _PHOTO_FORMATS:
                raise MediaError("media.photo_type")
            # Checked from the header, before the pixels are decoded.
            width, height = image.size
            if width * height > config.PHOTO_MAX_PIXELS:
                raise MediaError("media.photo_too_big")
            # A JPEG is decoded at a reduced scale when it is far bigger than the size sent, so a
            # large photo does not take hundreds of MB of memory.
            image.draft("RGB", side)
            image.load()
            upright = ImageOps.exif_transpose(image)
            if upright.mode in ("P", "1"):
                # Pillow scales these modes with nearest-neighbour only; converted first, a palette
                # or 1-bit PNG is scaled down smoothly.
                upright = upright.convert("RGBA")
            upright.thumbnail(side)
            rgba = upright.convert("RGBA")
    except MediaError:
        raise
    except UnidentifiedImageError:
        # Neither a JPEG nor a PNG (or not an image at all): no other parser is tried.
        raise MediaError("media.photo_type") from None
    except Image.DecompressionBombError, OSError, ValueError:
        raise MediaError("media.photo_unreadable") from None
    # A new image gets only the pixels: none of the file's info (EXIF, XMP, ICC, comments) is
    # carried over, and save() is given none.
    clean = Image.new("RGB", rgba.size, _BACKGROUND)
    clean.paste(rgba, mask=rgba.getchannel("A"))
    out = io.BytesIO()
    clean.save(out, format="JPEG", quality=config.PHOTO_JPEG_QUALITY)
    return out.getvalue()


def clean_voice(data: bytes) -> bytes:
    """Return a voice note re-written as a WAV of its samples only; MediaError if it cannot be."""
    if not data:
        raise MediaError("media.voice_unreadable")
    if len(data) > config.VOICE_MAX_BYTES:
        raise MediaError("media.voice_too_long")
    try:
        with wave.open(io.BytesIO(data), "rb") as recording:
            channels = recording.getnchannels()
            width = recording.getsampwidth()
            rate = recording.getframerate()
            frames = recording.getnframes()
            if channels < 1 or width not in _SAMPLE_WIDTHS:
                raise MediaError("media.voice_unreadable")
            if rate <= 0 or frames / rate > config.VOICE_MAX_SECONDS:
                raise MediaError("media.voice_too_long")
            samples = recording.readframes(frames)
    except MediaError:
        raise
    except wave.Error, EOFError, OSError, ValueError:
        raise MediaError("media.voice_unreadable") from None
    if not samples:
        raise MediaError("media.voice_empty")
    out = io.BytesIO()
    # Only the format and the samples: wave writes a RIFF header, a fmt chunk and a data chunk.
    with wave.open(out, "wb") as clean:
        clean.setnchannels(channels)
        clean.setsampwidth(width)
        clean.setframerate(rate)
        clean.writeframes(samples)
    return out.getvalue()


def _first_call_message(kind: Kind, data: bytes) -> HumanMessage:
    """Return the client's turn of the first call: the cleaned file alone, as data."""
    encoded = base64.b64encode(data).decode("ascii")
    if kind == "photo":
        block = {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}}
    else:
        block = {"type": "input_audio", "input_audio": {"data": encoded, "format": "wav"}}
    return HumanMessage(content=[block])


def first_call_messages(kind: Kind, prompt_text: str, data: bytes) -> list[BaseMessage]:
    """Return the first call's input: the owner's fixed instruction, then the cleaned file only."""
    return [SystemMessage(prompt_text), _first_call_message(kind, data)]


def reply_text(reply: object) -> str:
    """Return a model reply's text, joined from its text blocks, or "" if it has none."""
    content = getattr(reply, "content", reply)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            block.get("text", "") if isinstance(block, dict) else block
            for block in content
            if isinstance(block, str) or (isinstance(block, dict) and block.get("type") == "text")
        ]
        return "".join(part for part in parts if isinstance(part, str)).strip()
    return ""


def is_nothing(text: str) -> bool:
    """Return True for an empty reading or the instructions' fixed answer for one (NONE)."""
    # The owner's instructions (O19) answer exactly NONE when there is nothing to describe or
    # transcribe; a run then ends without the draft call. A period or quotes around it count too.
    return text.strip().strip(".\"'`").strip().upper() in ("", NOTHING_REPLY)


def read_media(model: BaseChatModel, kind: Kind, prompt_text: str, data: bytes) -> str:
    """Send the cleaned file with the fixed instruction and return the model's text."""
    with llm.mapped_errors():
        reply = model.invoke(first_call_messages(kind, prompt_text, data))
    return reply_text(reply)


def build_model(kind: Kind, *, api_key: str | None = None, http_client=None) -> BaseChatModel:
    """Build the first call's client: its model, cap and the providers consent (c) names."""
    # The one place either client is built, so the provider pin that keeps consent (c)'s text true
    # cannot be left out.
    return llm.build_chat_model(
        config.PHOTO_MODEL if kind == "photo" else config.VOICE_MODEL,
        config.MEDIA_MAX_TOKENS,
        providers=config.MEDIA_PROVIDERS,
        api_key=api_key,
        http_client=http_client,
    )


def model_provider() -> str:
    """Return the providers the flow's models are pinned to, as the consent shows them."""
    # Both calls count: the first call's models and the draft model the passed text goes to, so a
    # provider added to either changes consent (c)'s text and version.
    names = {"openai": "OpenAI", "azure": "Microsoft Azure"}
    slugs = dict.fromkeys((*config.MEDIA_PROVIDERS, *config.DRAFT_PROVIDERS))
    return " / ".join(names.get(slug, slug) for slug in slugs)


def consent_text(lang: i18n.Language) -> str:
    """Return consent (c)'s text in a language, naming OpenRouter and the models' provider."""
    return i18n.t(
        CONSENT_TEXT_KEY,
        lang,
        provider=model_provider(),
        mb=config.PHOTO_MAX_MB,
        seconds=config.VOICE_MAX_SECONDS,
    )


def consent_version() -> str:
    """Return the version of consent (c)'s text: both languages, so either changing asks again."""
    return chat.prompt_version(consent_text("en") + "\n" + consent_text("de"))
