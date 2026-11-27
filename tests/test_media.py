"""A photo or a voice note, checked and cleaned in memory before the first call (T11.10, D29)."""

import asyncio
import base64
import io
import json
import struct
import tempfile
import tomllib
import wave

import pytest
from PIL import ExifTags, Image, PngImagePlugin
from starlette.formparsers import MultiPartParser
from starlette.requests import Request
from streamlit.web.server.starlette import starlette_routes

from src import config, i18n, media
from tests.test_llm import CHAT_OK, FAKE_KEY, Recorder

CANARY = b"CANARY-MEDIA-7731"


def _jpeg_with_gps(size=(64, 48), orientation: int | None = None) -> bytes:
    """Return a JPEG with a GPS position, a camera make, a comment and maybe an orientation."""
    exif = Image.Exif()
    exif[ExifTags.Base.Make] = "CanaryPhone"
    exif[ExifTags.Base.DateTimeOriginal] = "2026:11:25 08:15:00"
    if orientation is not None:
        exif[ExifTags.Base.Orientation] = orientation
    gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
    gps[ExifTags.GPS.GPSLatitudeRef] = "N"
    gps[ExifTags.GPS.GPSLatitude] = (52.0, 31.0, 12.0)
    gps[ExifTags.GPS.GPSLongitudeRef] = "E"
    gps[ExifTags.GPS.GPSLongitude] = (13.0, 24.0, 18.0)
    out = io.BytesIO()
    Image.new("RGB", size, (200, 120, 40)).save(out, format="JPEG", exif=exif, comment=CANARY)
    return out.getvalue()


def _png(size=(40, 30), mode="RGBA") -> bytes:
    """Return a PNG with a text chunk holding the canary."""
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", CANARY.decode())
    out = io.BytesIO()
    Image.new(mode, size, (10, 200, 30, 128) if mode == "RGBA" else (10, 200, 30)).save(
        out, format="PNG", pnginfo=info
    )
    return out.getvalue()


def _samples(seconds: float, rate: int = config.VOICE_SAMPLE_RATE) -> bytes:
    """Return 16-bit mono samples of a quiet ramp, so the samples can be told apart."""
    count = int(seconds * rate)
    return b"".join(struct.pack("<h", (index % 200) - 100) for index in range(count))


def _wav(seconds: float = 1.0, rate: int = config.VOICE_SAMPLE_RATE) -> bytes:
    """Return a plain 16-bit mono WAV."""
    out = io.BytesIO()
    with wave.open(out, "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(rate)
        recording.writeframes(_samples(seconds, rate))
    return out.getvalue()


def _chunk(name: bytes, body: bytes) -> bytes:
    """Return a RIFF chunk, padded to an even size."""
    return name + struct.pack("<I", len(body)) + body + (b"\x00" if len(body) % 2 else b"")


def _tagged_wav(seconds: float = 1.0) -> bytes:
    """Return a WAV with a LIST/INFO tag chunk (title, artist) before its data, as recorders do."""
    plain = _wav(seconds)
    fmt = plain[12:36]  # the fmt chunk wave wrote
    data = plain[36:]  # the data chunk
    tags = _chunk(b"LIST", b"INFO" + _chunk(b"INAM", CANARY + b"\x00") + _chunk(b"IART", b"Me\x00"))
    body = b"WAVE" + fmt + tags + data
    return b"RIFF" + struct.pack("<I", len(body)) + body


# --- Photos -------------------------------------------------------------------------------------


def test_a_jpeg_with_a_gps_position_leaves_the_app_without_it():
    """The GPS position, camera make, time and comment are gone; the pixels stay."""
    original = _jpeg_with_gps()
    with Image.open(io.BytesIO(original)) as before:
        assert before.getexif().get_ifd(ExifTags.IFD.GPSInfo)  # the test photo has a position
    cleaned = media.clean_photo(original)
    with Image.open(io.BytesIO(cleaned)) as after:
        assert after.format == "JPEG"
        assert after.size == (64, 48)
        assert not after.getexif()
        assert not after.getexif().get_ifd(ExifTags.IFD.GPSInfo)
        assert "exif" not in after.info and "comment" not in after.info
        assert "icc_profile" not in after.info
    assert b"Exif" not in cleaned and CANARY not in cleaned and b"CanaryPhone" not in cleaned


def test_a_png_becomes_a_jpeg_without_its_text_chunks():
    """A PNG (with transparency) is re-encoded as a JPEG; its text chunk is not carried over."""
    cleaned = media.clean_photo(_png())
    with Image.open(io.BytesIO(cleaned)) as after:
        assert after.format == "JPEG" and after.mode == "RGB" and after.size == (40, 30)
    assert CANARY not in cleaned


def test_the_photo_is_turned_upright_before_its_orientation_tag_is_dropped():
    """A photo tagged as rotated is sent upright, as the gymer saw it."""
    cleaned = media.clean_photo(_jpeg_with_gps(size=(60, 20), orientation=6))
    with Image.open(io.BytesIO(cleaned)) as after:
        assert after.size == (20, 60)


def test_a_big_photo_is_scaled_down_to_the_configured_side():
    """The longer side is at most config.PHOTO_MAX_SIDE_PX, the shape kept."""
    out = io.BytesIO()
    Image.new("RGB", (3200, 2000), (1, 2, 3)).save(out, format="JPEG")
    with Image.open(io.BytesIO(media.clean_photo(out.getvalue()))) as after:
        assert max(after.size) == config.PHOTO_MAX_SIDE_PX
        assert after.size == (config.PHOTO_MAX_SIDE_PX, 1000)


def test_a_photo_over_the_size_limit_is_refused_before_it_is_read(monkeypatch):
    """A file over config.PHOTO_MAX_BYTES is refused without decoding it."""
    monkeypatch.setattr(Image, "open", lambda *args, **kwargs: pytest.fail("decoded"))
    with pytest.raises(media.MediaError) as refused:
        media.clean_photo(b"\xff\xd8" + b"0" * config.PHOTO_MAX_BYTES)
    assert refused.value.code == "media.photo_too_big"


def test_a_photo_with_too_many_pixels_is_refused_before_its_pixels_are_decoded(monkeypatch):
    """A small file that would decode to a huge image is refused from its header."""
    monkeypatch.setattr(config, "PHOTO_MAX_PIXELS", 100)
    with pytest.raises(media.MediaError) as refused:
        media.clean_photo(_png(size=(20, 20)))
    assert refused.value.code == "media.photo_too_big"


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"", "media.photo_unreadable"),
        (b"not an image at all", "media.photo_type"),
        (_jpeg_with_gps()[:200], "media.photo_unreadable"),
    ],
    ids=["empty", "garbage", "cut_off"],
)
def test_a_file_that_is_no_photo_is_refused(data, code):
    """Empty, garbage or cut-off bytes are refused with a fixed code."""
    with pytest.raises(media.MediaError) as refused:
        media.clean_photo(data)
    assert refused.value.code == code


@pytest.mark.parametrize("image_format", ["GIF", "BMP", "WEBP"])
def test_another_image_type_is_refused_whatever_its_name(image_format):
    """Only JPEG and PNG content is taken, read from the bytes, not the file's name."""
    out = io.BytesIO()
    Image.new("RGB", (8, 8)).save(out, format=image_format)
    with pytest.raises(media.MediaError) as refused:
        media.clean_photo(out.getvalue())
    assert refused.value.code == "media.photo_type"


def test_only_pillow_s_jpeg_and_png_parsers_read_the_bytes(monkeypatch):
    """Image.open is asked for the two formats only, so no other parser sees untrusted bytes."""
    asked = []
    real = Image.open

    def spy(fp, mode="r", formats=None):
        """Record the formats asked for, then open as Pillow does."""
        asked.append(formats)
        return real(fp, mode, formats)

    monkeypatch.setattr(Image, "open", spy)
    media.clean_photo(_png())
    assert asked == [("JPEG", "PNG")]


def test_a_jpeg_holding_a_second_image_is_taken_and_sent_as_one_image():
    """A JPEG with an MPF second image (a preview, a gain map) opens as MPO; its first goes."""
    out = io.BytesIO()
    first = Image.new("RGB", (40, 30), (250, 10, 10))
    first.save(out, format="MPO", save_all=True, append_images=[Image.new("RGB", (40, 30))])
    with Image.open(io.BytesIO(out.getvalue())) as before:
        assert before.format == "MPO" and before.n_frames == 2
    cleaned = media.clean_photo(out.getvalue())
    with Image.open(io.BytesIO(cleaned)) as after:
        assert after.format == "JPEG" and getattr(after, "n_frames", 1) == 1
        assert after.getpixel((20, 15))[0] > 200  # the first image's red, not the black second


# --- Voice notes --------------------------------------------------------------------------------


def test_a_voice_note_leaves_the_app_without_its_tags_and_with_its_samples():
    """The LIST/INFO chunk is dropped; the format and every sample are kept."""
    original = _tagged_wav()
    assert b"LIST" in original and CANARY in original
    cleaned = media.clean_voice(original)
    assert b"LIST" not in cleaned and b"INFO" not in cleaned and CANARY not in cleaned
    with wave.open(io.BytesIO(cleaned), "rb") as after:
        assert after.getnchannels() == 1
        assert after.getsampwidth() == 2
        assert after.getframerate() == config.VOICE_SAMPLE_RATE
        assert after.readframes(after.getnframes()) == _samples(1.0)
    # Only the RIFF header, the fmt chunk and the data chunk.
    assert cleaned[:4] == b"RIFF" and cleaned[12:16] == b"fmt " and cleaned[36:40] == b"data"


def test_a_wav_with_a_sample_width_wave_cannot_write_is_refused():
    """A WAV declaring 64-bit samples (read by wave, not written) gets the fixed refusal."""
    plain = bytearray(_wav(0.1))
    # The fmt chunk's block align (offset 32) and bits per sample (offset 34): 8 bytes, 64 bits.
    plain[32:34] = struct.pack("<H", 8)
    plain[34:36] = struct.pack("<H", 64)
    with pytest.raises(media.MediaError) as refused:
        media.clean_voice(bytes(plain))
    assert refused.value.code == "media.voice_unreadable"


def test_a_voice_note_of_exactly_the_limit_is_taken():
    """config.VOICE_MAX_SECONDS seconds pass; the limit is inclusive."""
    cleaned = media.clean_voice(_wav(config.VOICE_MAX_SECONDS, rate=8000))
    with wave.open(io.BytesIO(cleaned), "rb") as after:
        assert after.getnframes() == config.VOICE_MAX_SECONDS * 8000


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (_wav(config.VOICE_MAX_SECONDS + 1, rate=8000), "media.voice_too_long"),
        (b"0" * (config.VOICE_MAX_BYTES + 1), "media.voice_too_long"),
        (b"", "media.voice_unreadable"),
        (b"RIFF not really a wave file", "media.voice_unreadable"),
        (_wav(0), "media.voice_empty"),
    ],
    ids=["too_long", "too_big", "empty_file", "not_wav", "no_samples"],
)
def test_a_voice_note_that_cannot_be_sent_is_refused(data, code):
    """Too long, too big, not a WAV or empty: a fixed code, before any model call."""
    with pytest.raises(media.MediaError) as refused:
        media.clean_voice(data)
    assert refused.value.code == code


# --- The first call -----------------------------------------------------------------------------


@pytest.mark.parametrize(("kind", "block"), [("photo", "image_url"), ("voice", "input_audio")])
def test_the_first_call_holds_the_fixed_instruction_and_the_file_only(kind, block):
    """A system message with the owner's text, then one block: the file; nothing else."""
    sent = media.first_call_messages(kind, "FIXED-INSTRUCTION", b"\x01\x02")
    assert [message.type for message in sent] == ["system", "human"]
    assert sent[0].content == "FIXED-INSTRUCTION"
    assert [part["type"] for part in sent[1].content] == [block]


@pytest.mark.parametrize("kind", ["photo", "voice"])
def test_the_request_sent_carries_the_cleaned_file_and_pins_the_provider(kind):
    """What leaves the app: the kind's model, the pin to OpenAI, the cleaned bytes, no tags."""
    server = Recorder(body=CHAT_OK)
    model = media.build_model(kind, api_key=FAKE_KEY, http_client=server.client())
    original = _jpeg_with_gps() if kind == "photo" else _tagged_wav()
    cleaned = media.clean_photo(original) if kind == "photo" else media.clean_voice(original)
    assert media.read_media(model, kind, "FIXED-INSTRUCTION", cleaned) == "Hello."
    body = server.last_json()
    assert body["model"] == (config.PHOTO_MODEL if kind == "photo" else config.VOICE_MODEL)
    assert body["provider"] == {"only": list(config.MEDIA_PROVIDERS), "allow_fallbacks": False}
    system, human = body["messages"]
    assert system["content"] == "FIXED-INSTRUCTION"
    [part] = human["content"]
    if kind == "photo":
        url = part["image_url"]["url"]
        assert url.startswith("data:image/jpeg;base64,")
        sent = base64.b64decode(url.split(",", 1)[1])
    else:
        assert part["input_audio"]["format"] == "wav"
        sent = base64.b64decode(part["input_audio"]["data"])
    assert sent == cleaned
    assert CANARY not in sent and b"Exif" not in sent and b"LIST" not in sent
    assert CANARY.decode() not in json.dumps(body)


@pytest.mark.parametrize(
    ("content", "text"),
    [
        ("  Two eggs.  ", "Two eggs."),
        ([{"type": "text", "text": "Two "}, {"type": "text", "text": "eggs."}], "Two eggs."),
        ([{"type": "reasoning", "text": "hidden"}], ""),
        (None, ""),
    ],
)
def test_the_reply_text_is_read_from_its_text_blocks_only(content, text):
    """Only the reply's text reaches the guard; other blocks are left out."""

    class Reply:
        """A reply with the given content."""

        def __init__(self, found):
            """Keep the content."""
            self.content = found

    assert media.reply_text(Reply(content)) == text


# --- Consent (c) --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("language", "needles"),
    [
        (
            "en",
            [
                "OpenRouter",
                "OpenAI",
                "whole file",
                "before any safety check",
                "other people",
                "documents and labels",
                "only your own voice",
                "5 MB",
                "60 seconds",
                "withdraw",
            ],
        ),
        (
            "de",
            [
                "OpenRouter",
                "OpenAI",
                "ganze Datei",
                "bevor eine Sicherheitsprüfung",
                "Personen",
                "Dokumente und Etiketten",
                "nur Ihre eigene Stimme",
                "5 MB",
                "60 Sekunden",
                "widerrufen",
            ],
        ),
    ],
)
def test_consent_c_names_the_recipients_the_unchecked_file_and_what_to_keep_out(language, needles):
    """The text says where the whole file goes before any check and what to keep out of it."""
    text = media.consent_text(language)
    for needle in needles:
        assert needle in text, needle


def test_consent_c_names_the_draft_model_s_providers_too(monkeypatch):
    """The passed text goes on to the draft model, so a provider added there changes (c)'s text."""
    before = media.consent_version()
    monkeypatch.setattr(config, "DRAFT_PROVIDERS", ("openai", "azure"))
    assert media.model_provider() == "OpenAI / Microsoft Azure"
    assert media.consent_version() != before


def test_consent_c_s_version_changes_with_its_text(monkeypatch):
    """Another provider changes the text in both languages, so the version asks again."""
    before = media.consent_version()
    monkeypatch.setattr(config, "MEDIA_PROVIDERS", ("openai", "azure"))
    assert "Microsoft Azure" in media.consent_text("en")
    assert media.consent_version() != before


def test_the_media_texts_exist_in_both_languages():
    """Every media key has an English and a German text."""
    keys = {key for key in i18n.TEXT["en"] if key.startswith("media.")}
    assert keys and keys <= set(i18n.TEXT["de"])


# --- Uploads stay in memory while the server reads them ----------------------------------------

CRLF = "\r\n"


def _form_upload(size: int):
    """Parse a multipart body with one file part of `size` bytes as Streamlit's server does."""
    boundary = "testboundary"
    head = CRLF.join(
        [
            f"--{boundary}",
            'Content-Disposition: form-data; name="file"; filename="m.jpg"',
            "Content-Type: image/jpeg",
            "",
            "",
        ]
    )
    body = head.encode() + b"\xff" * size + f"{CRLF}--{boundary}--{CRLF}".encode()
    scope = {
        "type": "http",
        "method": "PUT",
        "headers": [(b"content-type", f"multipart/form-data; boundary={boundary}".encode())],
    }
    sent = [False]

    async def receive():
        """Give the whole body once."""
        if sent[0]:
            return {"type": "http.disconnect"}
        sent[0] = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def parse():
        """Return the parsed file part."""
        form = await Request(scope, receive).form()
        return form["file"]

    return asyncio.run(parse())


def test_an_upload_of_the_largest_allowed_size_stays_in_memory(monkeypatch, tmp_path):
    """With the spool raised, a 5 MB part is never rolled over into a temporary file."""
    monkeypatch.setattr(MultiPartParser, "spool_max_size", MultiPartParser.spool_max_size)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    media.keep_uploads_in_memory()
    upload = _form_upload(config.PHOTO_MAX_BYTES)
    assert upload.file._rolled is False
    assert list(tmp_path.iterdir()) == []


def test_without_the_raised_spool_the_same_upload_would_reach_the_disk(monkeypatch, tmp_path):
    """The control: Starlette's default writes that part to a temporary file."""
    monkeypatch.setattr(MultiPartParser, "spool_max_size", 1024 * 1024)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    upload = _form_upload(config.PHOTO_MAX_BYTES)
    assert upload.file._rolled is True


def test_the_server_s_upload_limit_matches_config_and_fits_the_spool():
    """config.toml's maxUploadSize is config.UPLOAD_MAX_MB, above both limits, below the spool."""
    settings = tomllib.loads(
        (config.PROJECT_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    )
    assert settings["server"]["maxUploadSize"] == config.UPLOAD_MAX_MB
    limit = config.UPLOAD_MAX_MB * 1024 * 1024
    assert config.PHOTO_MAX_BYTES < limit and config.VOICE_MAX_BYTES < limit
    overhead = starlette_routes._MAX_UPLOAD_MULTIPART_OVERHEAD_BYTES
    assert config.UPLOAD_SPOOL_MAX_BYTES >= limit + overhead


@pytest.mark.parametrize("path", [config.PHOTO_PROMPT_PATH, config.VOICE_PROMPT_PATH])
def test_the_owner_s_instructions_name_the_code_s_limit_and_none(path):
    """Each instruction asks for at most the guard's limit and answers NONE as the code reads it."""
    text = path.read_text(encoding="utf-8")
    assert str(config.MEDIA_TEXT_MAX_CHARS) in text
    assert media.NOTHING_REPLY in text and media.is_nothing(media.NOTHING_REPLY)
