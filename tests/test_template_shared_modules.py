"""The modules the project template shares with the launcher (#309).

They're linked into the template and copied into every new project, so they
must import only what such a project has: the standard library, Toga, Rubicon,
Chaquopy's Java bridge, and each other. ``togax_jkingok`` is allowed only as an
optional import with a fallback, since a standalone project doesn't have it.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from mypystub import hooks, run_status

TEMPLATE = (
    Path(__file__).parent.parent
    / "src/mypystub/resources/templates/project/src/app_template"
)
LINKED = sorted(p for p in TEMPLATE.glob("*.py") if p.is_symlink())
ALLOWED = {"toga", "travertino", "rubicon", "java", "com"}
OPTIONAL = {"togax_jkingok", "toga_console"}


def test_the_script_view_is_shared_not_copied() -> None:
    names = {p.name for p in LINKED}
    assert {"hooks.py", "script_tab.py", "run_status.py", "logfile.py"} <= names
    assert not (TEMPLATE / "script_view.py").exists()


def _guarded(tree: ast.Module) -> set[int]:
    """Line numbers of imports inside ``try: … except ImportError``."""
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and any(
            isinstance(h.type, ast.Name) and h.type.id == "ImportError"
            for h in node.handlers
        ):
            for inner in node.body:
                for sub in ast.walk(inner):
                    if isinstance(sub, (ast.Import, ast.ImportFrom)):
                        lines.add(sub.lineno)
    return lines


@pytest.mark.parametrize("path", LINKED, ids=lambda p: p.name)
def test_linked_modules_import_only_what_a_project_has(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    guarded = _guarded(tree)
    siblings = {p.stem for p in LINKED}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            names = [node.module] if node.module else [a.name for a in node.names]
            assert all(n.split(".")[0] in siblings for n in names), (
                f"{path.name}:{node.lineno} imports an unlinked module"
            )
            continue
        if isinstance(node, ast.Import):
            tops = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            tops = [(node.module or "").split(".")[0]]
        else:
            continue
        for top in tops:
            if top in sys.stdlib_module_names or top == "__future__":
                continue
            if top in ALLOWED or top.startswith("toga_"):
                continue
            assert top in OPTIONAL and node.lineno in guarded, (
                f"{path.name}:{node.lineno} imports {top}"
            )


@pytest.mark.parametrize("path", LINKED, ids=lambda p: p.name)
def test_shared_docstrings_dont_speak_of_the_launcher(path: Path) -> None:
    """A project's own users read these; MyPyStub is named, not 'the launcher'."""
    if path.name == "android_back.py":
        pytest.skip("shared before #309; its own wording")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            doc = ast.get_docstring(node) or ""
            assert "the launcher" not in doc.lower(), f"{path.name}: {doc[:60]}"


def frame(module: str) -> SimpleNamespace:
    return SimpleNamespace(f_globals={"__name__": module})


def test_a_project_names_its_own_start_up_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The app shares a package with its bootstrap; only the app's writes show."""
    monkeypatch.setattr(hooks, "_framework", hooks._framework)
    hooks.set_framework("weather.bootstrap", "weather.hooks")
    assert hooks.frame_owner(frame("weather.app")) is True
    assert hooks.frame_owner(frame("weather.bootstrap")) is False
    assert hooks.frame_owner(frame("weather.hooks")) is False
    assert hooks.frame_owner(frame("toga.widgets.base")) is False
    assert hooks.frame_owner(frame("toga_iOS.app")) is False
    assert hooks.frame_owner(frame("json")) is None
    assert hooks.frame_owner(frame("mypystub.ui")) is True  # not named here


def test_by_default_mypystub_is_the_framework() -> None:
    assert hooks.frame_owner(frame("mypystub.ui")) is False
    assert hooks.frame_owner(frame("weather.bootstrap")) is True


def test_run_status_needs_no_launcher() -> None:
    class Refused(Exception):
        could_not_run = True

    assert run_status.run_status(Refused()) == "⚠️ Couldn't run"
    assert run_status.run_status(ValueError()) == "❌ Failed: ValueError"
    assert run_status.run_status(None) == run_status.FINISHED
