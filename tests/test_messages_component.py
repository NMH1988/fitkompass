"""Tests for the Messages page's browser component (T11.4b): its JavaScript and its mounting.

The socket logic is tested with Node's built-in test runner (`tests/js/messages.test.mjs`, no npm
package): this file runs it, and skips when Node is not installed, except in CI (GitHub's runners
have Node), where a missing Node fails. The other tests read the component's code: it loads nothing
from another host, keeps the token out of the browser's storage and the page's state, and shows
text only as text; and the page mounts it inside an `st.fragment` with a fixed key.
"""

import ast
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "views" / "components" / "messages.mjs"
STYLES = ROOT / "views" / "components" / "messages.css"
NODE_TESTS = ROOT / "tests" / "js" / "messages.test.mjs"


def _code_only(text: str) -> str:
    """Return the JavaScript with its comments removed, so a word in a comment is not a finding."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return "\n".join(re.sub(r"(^|\s)//.*$", "", line) for line in text.splitlines())


def test_the_component_s_socket_logic_passes_its_node_tests():
    """`node --test` on the component's tests passes (renewal, reconnect, de-duplication, caps)."""
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("Node is missing in CI: the component's tests did not run")
        pytest.skip("Node is not installed")
    done = subprocess.run(
        [node, "--test", str(NODE_TESTS)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, (done.stdout + done.stderr)[-4000:]
    assert re.search(r"pass (\d+)", done.stdout).group(1) != "0"


@pytest.mark.parametrize(
    "forbidden",
    [
        # Nothing loaded or sent anywhere but the page's own socket.
        "http://",
        "https://",
        "import(",
        "fetch(",
        "XMLHttpRequest",
        "sendBeacon",
        "EventSource",
        # The token stays in memory: not in the browser's storage, a cookie or the page's state.
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "document.cookie",
        "setStateValue",
        "history.",
        "location.hash",
        "location.search",
        # Text is shown as text, never parsed as HTML or run as code.
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "eval(",
        "new Function",
        "console.",
    ],
)
def test_the_component_loads_nothing_and_keeps_the_token_in_memory(forbidden):
    """The component's code holds no URL, storage, HTML parsing or logging."""
    assert forbidden not in _code_only(COMPONENT.read_text(encoding="utf-8"))


def test_the_component_imports_nothing_and_its_styles_load_nothing():
    """No import statement in the component, and no url() or @import in its styles."""
    code = _code_only(COMPONENT.read_text(encoding="utf-8"))
    assert not re.search(r"^\s*import\s", code, flags=re.MULTILINE)
    styles = STYLES.read_text(encoding="utf-8")
    assert "url(" not in styles and "@import" not in styles


def test_the_socket_s_url_is_the_page_s_own_host():
    """The socket is opened on window.location's host, wss:// on an https page."""
    code = _code_only(COMPONENT.read_text(encoding="utf-8"))
    assert "window.location.host" in code and '"wss:"' in code and "new WebSocket(url)" in code


def _thread_function(tree: ast.Module) -> ast.FunctionDef:
    """Return the page's function that mounts the component."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            for call in ast.walk(node):
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == "_COMPONENT"
                ):
                    return node
    raise AssertionError("no function mounts the component")


def test_the_page_mounts_the_component_inside_a_fragment_with_a_fixed_key():
    """The component is in an st.fragment (a renewal reruns only it) and keyed by the thread."""
    tree = ast.parse((ROOT / "views" / "messages.py").read_text(encoding="utf-8"))
    function = _thread_function(tree)
    decorators = [ast.unparse(decorator) for decorator in function.decorator_list]
    assert decorators == ["st.fragment"]
    [call] = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        if node.func.id == "_COMPONENT"
    ]
    keywords = {keyword.arg: ast.unparse(keyword.value) for keyword in call.keywords}
    assert keywords["key"] == "component_key(thread_id)"
    assert keywords["on_renew_change"] == "lambda: None"
