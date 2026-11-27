"""UI tests for the AI drafts from a photo or a voice note on the Today page (T11.10, AC-51)."""

import io
import json

import pytest
from PIL import Image
from starlette.formparsers import MultiPartParser
from streamlit.testing.v1 import AppTest

from src import config, media
from src.store import ai_consents, db
from tests.fakes import ScriptedMediaModel, ScriptedTranslator
from tests.test_app_account import PROFILE, USER_ID, signed_in, start, store_account, texts
from tests.test_app_today import open_today
from views import media_drafts, resources

pytestmark = pytest.mark.usefixtures("no_env_key")

EGG = "Egg, whole, raw, frozen, pasteurized"
DESCRIPTION = "CANARY-DESC Two eggs, about 100 g."


def _reply() -> str:
    """Return a draft model reply with one food."""
    return json.dumps(
        {
            "foods": [{"food": EGG, "grams": 100.0, "meal": "breakfast"}],
            "weight": None,
            "workout": [],
        }
    )


def _photo(image_format: str = "JPEG") -> bytes:
    """Return a small image in the format (a JPEG by default)."""
    out = io.BytesIO()
    Image.new("RGB", (32, 24), (240, 220, 180)).save(out, format=image_format)
    return out.getvalue()


class _Uploaded:
    """Stands in for the file a widget returns: only getvalue() is used."""

    def __init__(self, data: bytes) -> None:
        """Keep the bytes."""
        self.data = data

    def getvalue(self) -> bytes:
        """Return the bytes."""
        return self.data


@pytest.fixture
def gymer(monkeypatch, tmp_path):
    """Store the signed-in gymer with a profile; point the three prompts at test files."""
    store_account("gymer", "Mia", profile=PROFILE)
    for name, setting in (
        ("photo.md", "PHOTO_PROMPT_PATH"),
        ("voice.md", "VOICE_PROMPT_PATH"),
        ("draft.md", "DRAFT_PROMPT_PATH"),
    ):
        path = tmp_path / name
        path.write_text(f"Test prompt {name}.", encoding="utf-8")
        monkeypatch.setattr(config, setting, path)


@pytest.fixture
def fakes(monkeypatch):
    """Replace both models with scripted fakes that record their requests."""
    first = ScriptedMediaModel(replies=[DESCRIPTION])
    draft = ScriptedTranslator(plans=[_reply()], model_name=config.DRAFT_MODEL)
    monkeypatch.setattr(resources, "media_model", lambda kind: first)
    monkeypatch.setattr(resources, "draft_model", lambda: draft)
    return first, draft


def _consent() -> None:
    """Give the signed-in gymer's consent (c) to the current text."""
    with db.connect() as conn:
        ai_consents.give(conn, USER_ID, media.PURPOSE, media.consent_version())


def _today(monkeypatch, language: str = "en") -> AppTest:
    """Run the app signed in and open Today."""
    return open_today(start(monkeypatch, user=signed_in(), language=language))


def _labels(at: AppTest) -> list[str]:
    """Return the labels of the page's buttons."""
    return [item.label for item in at.button]


def _meals() -> int:
    """Return how many food entries the signed-in gymer has."""
    with db.connect() as conn:
        query = "SELECT count(*) FROM meal_items WHERE user_id = ?"
        return conn.execute(query, (USER_ID,)).fetchone()[0]


def _source(at: AppTest):
    """Return the source choice, or None when it is not drawn."""
    found = [item for item in at.button_group if item.label in ("Draft from", "Entwurf aus")]
    return found[0] if found else None


def _widgets(at: AppTest, kind: str) -> list:
    """Return the page's elements of a widget type (camera_input, audio_input, file_uploader)."""
    return at.get(kind)


@pytest.mark.parametrize(
    ("language", "consent", "give"),
    [
        (
            "en",
            "Consent (Art. 9 GDPR) to drafts of log entries from your photos",
            "Give this consent",
        ),
        (
            "de",
            "Einwilligung (Art. 9 DSGVO) in Entwürfe von Tagebucheinträgen aus Ihren Fotos",
            "Einwilligung erteilen",
        ),
    ],
)
def test_without_consent_c_there_is_no_upload_camera_or_recorder(
    monkeypatch, gymer, fakes, language, consent, give
):
    """Only the consent's text and its button show; one click gives it and sends nothing."""
    monkeypatch.setattr(MultiPartParser, "spool_max_size", 1024 * 1024)
    at = _today(monkeypatch, language)
    # Opening Today raises the upload spool before any upload widget can be drawn.
    assert MultiPartParser.spool_max_size >= config.UPLOAD_SPOOL_MAX_BYTES
    page = texts(at)
    assert consent in page and "OpenRouter" in page and "OpenAI" in page
    assert _source(at) is None
    for kind in ("camera_input", "audio_input", "file_uploader"):
        assert _widgets(at, kind) == [], kind
    [button] = [item for item in at.button if item.label == give]
    button.click()
    at.run(timeout=30)
    with db.connect() as conn:
        assert ai_consents.is_given(conn, USER_ID, media.PURPOSE, media.consent_version())
    first, draft = fakes
    assert first.calls == [] and draft.calls == []


@pytest.mark.parametrize("language", ["en", "de"])
def test_the_camera_opens_only_once_chosen_and_under_the_warning(
    monkeypatch, gymer, fakes, language
):
    """With consent: no camera on the page load; choosing it draws it, with the warning shown."""
    _consent()
    at = _today(monkeypatch, language)
    warning = "documents and labels" if language == "en" else "Dokumente und Etiketten"
    assert warning in texts(at)
    assert _source(at) is not None and _source(at).value is None
    assert _widgets(at, "camera_input") == []
    _source(at).set_value("camera")
    at.run(timeout=30)
    assert len(_widgets(at, "camera_input")) == 1
    assert warning in texts(at)
    _source(at).set_value("upload")
    at.run(timeout=30)
    assert _widgets(at, "camera_input") == [] and len(_widgets(at, "file_uploader")) == 1
    assert warning in texts(at)


@pytest.mark.parametrize(
    ("language", "staged", "synthetic"),
    [
        ("en", "staged meal", "synthetic recording"),
        ("de", "gestellte Mahlzeit", "synthetische Aufnahme"),
    ],
)
def test_each_source_asks_for_staged_photos_and_synthetic_recordings(
    monkeypatch, gymer, fakes, language, staged, synthetic
):
    """While the app holds made-up data: the page and each widget's help say what to send."""
    _consent()
    at = _today(monkeypatch, language)
    page = texts(at)
    assert staged in page and synthetic in page
    for source, kind, needle in (
        ("upload", "file_uploader", staged),
        ("camera", "camera_input", staged),
        ("voice", "audio_input", synthetic),
    ):
        _source(at).set_value(source)
        at.run(timeout=30)
        [widget] = _widgets(at, kind)
        assert needle in widget.proto.help, (source, language)


def test_the_upload_takes_only_jpg_and_png_up_to_the_limit(monkeypatch, gymer, fakes):
    """The uploader names the types and the size limit from config."""
    _consent()
    at = _today(monkeypatch)
    _source(at).set_value("upload")
    at.run(timeout=30)
    [uploader] = _widgets(at, "file_uploader")
    assert set(uploader.proto.type) >= {".jpg", ".jpeg", ".png"}
    assert f"{config.PHOTO_MAX_MB} MB" in uploader.proto.label


def test_the_recorder_is_the_browser_s_widget_with_the_configured_rate(monkeypatch, gymer, fakes):
    """A voice note is recorded on the page, never uploaded as a file."""
    _consent()
    at = _today(monkeypatch)
    _source(at).set_value("voice")
    at.run(timeout=30)
    assert len(_widgets(at, "audio_input")) == 1
    assert _widgets(at, "file_uploader") == []
    assert f"{config.VOICE_MAX_SECONDS} seconds" in _widgets(at, "audio_input")[0].proto.label


def _press_with(monkeypatch, at: AppTest, kind: str, data: bytes) -> AppTest:
    """Stand in for a chosen file, then press the draft button."""
    monkeypatch.setattr(media_drafts, "_chosen_file", lambda: (kind, _Uploaded(data)))
    at.run(timeout=30)
    [button] = [item for item in at.button if item.key == "media_start"]
    button.click()
    return at.run(timeout=30)


def test_a_photo_becomes_a_card_labelled_as_ai_and_nothing_is_logged_before_save(
    monkeypatch, gymer, fakes
):
    """The card says an AI drafted it, shows what the AI saw, and logs only on Save."""
    _consent()
    at = _today(monkeypatch)
    before = _meals()
    at = _press_with(monkeypatch, at, "photo", _photo())
    page = texts(at)
    assert "Drafted by an AI model (OpenAI through OpenRouter) from your photo" in "\n".join(
        str(item.value) for item in at.info
    )
    assert DESCRIPTION in "\n".join(str(item.value) for item in at.text)
    assert "What the AI saw in your photo" in page
    assert _meals() == before
    first, draft = fakes
    assert len(first.calls) == 1 and len(draft.calls) == 1
    [action] = [item for item in at.button_group if item.label == "Decision"]
    action.set_value("approve")
    [save] = [item for item in at.button if item.label == "Save decisions"]
    save.click()
    at.run(timeout=30)
    assert _meals() == before + 1
    assert "Entries logged: 1" in "\n".join(str(item.value) for item in at.success)


@pytest.mark.parametrize(
    ("kind", "data", "message"),
    [
        ("photo", _photo("GIF"), "Only JPG and PNG photos"),
        ("photo", b"\xff\xd8" + b"0" * (config.PHOTO_MAX_BYTES + 1), "This photo is too big"),
        ("voice", b"not a recording", "This recording could not be read"),
    ],
    ids=["wrong_type", "too_big", "not_wav"],
)
def test_a_file_over_the_limit_or_of_another_type_is_refused_before_any_call(
    monkeypatch, gymer, fakes, kind, data, message
):
    """The checks run on the press, before the first call: no model is called."""
    _consent()
    at = _press_with(monkeypatch, _today(monkeypatch), kind, data)
    assert message in "\n".join(str(item.value) for item in at.error)
    first, draft = fakes
    assert first.calls == [] and draft.calls == []


def test_withdrawing_consent_c_drops_the_pending_cards(monkeypatch, gymer, fakes):
    """One click withdraws it; the cards go at once and the source choice is gone."""
    _consent()
    at = _press_with(monkeypatch, _today(monkeypatch), "photo", _photo())
    assert [item for item in at.button_group if item.label == "Decision"]
    [withdraw] = [item for item in at.button if item.key == "media_withdraw"]
    withdraw.click()
    at.run(timeout=30)
    with db.connect() as conn:
        assert not ai_consents.is_given(conn, USER_ID, media.PURPOSE, media.consent_version())
    assert not [item for item in at.button_group if item.label == "Decision"]
    assert _source(at) is None
