"""The app's name: FitKompass (T11.2) everywhere the current text and code name the app.

T9.22 renamed "Nutrition AI Assistant" to "Fitcoach AI Assistant"; T11.2 renames that to FitKompass,
with the tracing flags, the LangSmith projects, the evaluation prefixes and the store file.
"""

import ast
import re
from pathlib import Path

import pytest

from src import config, i18n
from src.config import paths
from src.config import tracing_requested as real_tracing_requested
from src.config.environment import tracing_demo_unmasked as real_tracing_demo_unmasked
from tests.fakes import patch_config

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app.py"
README = ROOT / "README.md"
PYPROJECT = ROOT / "pyproject.toml"
# The names before T9.22, matched case-sensitively, so the old repository's URL
# (`nutrition-ai-assistant`), kept as a record in the `#<n>` notes, does not match, nor does the
# guard's German role word "Ernährungsassistent" (src/guard.py).
OLD_NAMES = ("Nutrition AI Assistant", "KI-Ernährungsassistent")
# The name before T11.2, in any case: it also catches the old flags (FITCOACH_TRACING), projects
# (fitcoach-ai-assistant) and file names (fitcoach.sqlite3).
SPRINT3_NAME = re.compile("fitcoach", re.IGNORECASE)
# Lines of the code scan allowed to keep the Sprint 3 name. The Question phase found none: the
# records that keep it (docs/progress/, done tickets, the Sprint 3 video script, the agents' links
# to the Sprint 3 repository's PRs) are outside the scan.
SPRINT3_NAME_ALLOWED: tuple[str, ...] = ()
# Only text files are read; the scanned folders hold nothing else today.
SCANNED_SUFFIXES = {".py", ".md"}
# The reviewer agents, whose descriptions name the app.
AGENT_NAMES = ("code", "security", "compliance")
# The one README line allowed to name the old names: the history line in its Documentation section.
HISTORY_MARK = "until 2026-10-30"


def _files_in(*folders: Path) -> list[Path]:
    """Return the text files under the folders, without Python's caches."""
    return [
        path
        for folder in folders
        for path in sorted(folder.rglob("*"))
        if path.is_file() and path.suffix in SCANNED_SUFFIXES and "__pycache__" not in path.parts
    ]


def _scanned_files() -> list[Path]:
    """Return the files whose text must not use the names before T9.22 (README's history aside)."""
    return [APP, README, *_files_in(ROOT / "src", ROOT / "views", ROOT / ".claude" / "agents")]


def _code_files() -> list[Path]:
    """Return the code and package files that must not name the app "Fitcoach" in any case."""
    return [APP, PYPROJECT, *_files_in(ROOT / "src", ROOT / "views", ROOT / "scripts")]


def _old_name_lines(paths: list[Path]) -> list[tuple[Path, str]]:
    """Return each (file, line) whose text holds a name before T9.22, matched case-sensitively."""
    return [
        (path, line)
        for path in paths
        for line in path.read_text(encoding="utf-8").splitlines()
        if any(name in line for name in OLD_NAMES)
    ]


def _sprint3_name_lines(paths: list[Path]) -> list[tuple[Path, str]]:
    """Return each (file, line) that names "Fitcoach" in any case and is not on the allowed list."""
    return [
        (path, line)
        for path in paths
        for line in path.read_text(encoding="utf-8").splitlines()
        if SPRINT3_NAME.search(line) and line.strip() not in SPRINT3_NAME_ALLOWED
    ]


def _section(text: str, heading: str) -> list[str]:
    """Return the lines of a Markdown section, from its `## ` heading to the next one."""
    lines = text.splitlines()
    start = lines.index(heading) + 1
    end = next((n for n in range(start, len(lines)) if lines[n].startswith("## ")), len(lines))
    return lines[start:end]


def test_the_app_title_is_the_new_name_in_both_languages():
    """The header, the tab and the PDF read `app.title`: the same name in English and German."""
    assert config.APP_TITLE == "FitKompass"
    for language in i18n.LANGUAGES:
        assert i18n.t("app.title", language) == config.APP_TITLE
        assert i18n.t("pdf.title", language).startswith(f"{config.APP_TITLE}: ")
        assert i18n.t("pdf.footer", language, page=1).startswith(f"{config.APP_TITLE} · ")


@pytest.mark.parametrize(
    ("language", "workspace", "agent"),
    [("en", "coaching workspace", "AI agent"), ("de", "Coaching-Arbeitsbereich", "KI-Agent")],
)
def test_the_intro_and_about_say_it_is_a_coaching_workspace_with_an_ai_agent(
    language, workspace, agent
):
    """The header's intro and the About text say what the app is, in both languages."""
    intro = i18n.t("app.intro", language)
    assert workspace in intro
    assert agent in intro
    scope = i18n.t("about.scope", language)
    assert scope.startswith(f"{config.APP_TITLE} ")
    assert workspace in scope
    assert agent in scope


def test_the_tab_title_is_the_app_title_in_the_session_language():
    """app.py passes `app.title` in the session's language to st.set_page_config (AppTest can't)."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    [call] = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "st.set_page_config"
    ]
    keywords = {keyword.arg: ast.unparse(keyword.value) for keyword in call.keywords}
    assert keywords["page_title"] == "i18n.t('app.title', st.session_state[i18n.SESSION_KEY])"


def test_the_names_before_t9_22_are_only_in_the_readme_history_line():
    """The current text never says "Nutrition AI Assistant", except README's one history line."""
    [(path, line)] = _old_name_lines(_scanned_files())
    assert path == README
    assert HISTORY_MARK in line
    assert line in _section(README.read_text(encoding="utf-8"), "## Documentation")


def test_the_code_and_package_never_name_fitcoach():
    """No "Fitcoach" in any case in src/, views/, scripts/, app.py or pyproject.toml."""
    assert _sprint3_name_lines(_code_files()) == []


def test_the_scans_cover_the_app_views_src_scripts_package_agents_and_readme():
    """Both scans read app.py, a view, src modules and a prompt; each adds its own files."""
    agents = [ROOT / ".claude" / "agents" / f"{name}-reviewer.md" for name in AGENT_NAMES]
    common = [
        APP,
        ROOT / "views" / "header.py",
        ROOT / "src" / "i18n" / "shared.py",
        ROOT / "src" / "config" / "environment.py",
        ROOT / "src" / "prompts" / "answer_system.md",
    ]
    assert {*common, *agents, README} <= set(_scanned_files())
    assert {*common, PYPROJECT, ROOT / "scripts" / "make_video.py"} <= set(_code_files())


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("# Nutrition AI Assistant", True),
        ("the Nutrition AI Assistant: a chatbot", True),
        ("https://github.com/NMH1988/nutrition-ai-assistant", False),
        ("a nutrition AI assistant", False),
        ("FitKompass", False),
        ('_DE_APP_TITLE = "KI-Ernährungsassistent"', True),
        ('"du bist jetzt mein Ernährungsassistent"', False),
    ],
)
def test_the_scan_matches_the_names_before_t9_22_case_sensitively(tmp_path, text, found):
    """The scan finds an old name as written, not the old repository's URL, lower case or a role."""
    path = tmp_path / "file.md"
    path.write_text(f"before\n{text}\nafter\n", encoding="utf-8")
    assert bool(_old_name_lines([path])) is found


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("Fitcoach AI Assistant", True),
        ('TRACING_FLAG_NAME = "FITCOACH_TRACING"', True),
        ('LANGSMITH_PROJECT = "fitcoach-ai-assistant"', True),
        ('STORE_PATH = STORE_DIR / "fitcoach.sqlite3"', True),
        ("FitKompass, a coaching workspace", False),
        ("plans that fit coaching", False),
    ],
)
def test_the_code_scan_matches_fitcoach_in_any_case(tmp_path, text, found):
    """The code scan finds "Fitcoach" in any case, in names, flags and files, not "fit coaching"."""
    path = tmp_path / "file.py"
    path.write_text(f"before\n{text}\nafter\n", encoding="utf-8")
    assert bool(_sprint3_name_lines([path])) is found


def test_the_tracing_projects_prefixes_and_store_file_use_the_new_name():
    """Flags, LangSmith projects, evaluation prefixes and the store file start with fitkompass."""
    assert config.TRACING_FLAG_NAME == "FITKOMPASS_TRACING"
    assert config.TRACING_DEMO_UNMASKED_FLAG_NAME == "FITKOMPASS_TRACING_DEMO_UNMASKED"
    assert config.LANGSMITH_PROJECT == "fitkompass"
    assert config.LANGSMITH_DEMO_PROJECT == "fitkompass-demo"
    assert config.EVAL_DATASET_PREFIX == "fitkompass-eval-"
    assert config.EVAL_EXPERIMENT_PREFIX == "fitkompass-eval"
    # conftest points config.STORE_PATH at a temporary file; the module keeps the real name.
    assert paths.STORE_PATH.name == "fitkompass.sqlite3"


def test_the_old_tracing_flag_alone_leaves_tracing_off(monkeypatch, secrets_from_file):
    """FITCOACH_TRACING, in the environment or secrets.toml, no longer turns tracing on."""
    monkeypatch.delenv(config.TRACING_FLAG_NAME, raising=False)
    monkeypatch.setenv("FITCOACH_TRACING", "true")
    secrets_from_file("FITCOACH_TRACING = true\n")
    assert not real_tracing_requested()
    # The new flag, set the same way, does turn it on.
    secrets_from_file(f"{config.TRACING_FLAG_NAME} = true\n")
    assert real_tracing_requested()


def test_the_old_demo_flag_alone_leaves_traces_masked(monkeypatch):
    """The old demo flag no longer opens the demo gate, even with tracing and demo mode on."""
    monkeypatch.setattr(config.st, "secrets", {})
    patch_config(monkeypatch, "tracing_requested", lambda: True)
    patch_config(monkeypatch, "demo_mode", lambda: True)
    monkeypatch.delenv(config.TRACING_DEMO_UNMASKED_FLAG_NAME, raising=False)
    monkeypatch.setenv("FITCOACH_TRACING_DEMO_UNMASKED", "true")
    assert not real_tracing_demo_unmasked()
    monkeypatch.setenv(config.TRACING_DEMO_UNMASKED_FLAG_NAME, "true")
    assert real_tracing_demo_unmasked()
