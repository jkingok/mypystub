"""UI tests for the launcher: navigating folders, Help, running with dependencies, the splash.

Skipped where toga_dummy isn't installed, such as on device.
"""

import os
import re
import shutil
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import piplike, ui
from tests.support_ui import (
    ICONS,
    fresh_stack,
    tap,
    titles,
)

# ---------------------------------------------------------------------------
# Folder navigation (#35)
# ---------------------------------------------------------------------------


def test_list_starts_with_the_categories(
    app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """There's no category selector: the list opens on Examples and Documents."""
    monkeypatch.setattr(app, "user_documents_dir", docs, raising=False)
    p = ui.Prototype(host_app=app, on_done=lambda _: None)
    fresh_stack(p)
    app.main_window.content = p.get_content()
    p.reload_menu(p.script_list)
    assert titles(p) == ["Examples", "Documents"]
    documents = p.script_list.data[1]
    assert documents.subtitle == "📁 1 · 🐍 1"  # a/ and top.py
    assert not hasattr(p, "dir_selection")


def test_folders_drill_down_and_back_up(
    proto: ui.Prototype, app: toga.App, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Folder rows open, and ".." goes up, finally back to the categories."""
    assert titles(proto) == ["..", "a", "top"]
    tap(proto, "a", monkeypatch, app)
    assert titles(proto) == ["..", "b"] and proto.subfolder == Path("a")
    tap(proto, "b", monkeypatch, app)
    assert titles(proto) == ["..", "deep"]
    tap(proto, "..", monkeypatch, app)
    assert proto.subfolder == Path("a")
    tap(proto, "..", monkeypatch, app)
    assert titles(proto) == ["..", "a", "top"] and proto.subfolder == Path()
    tap(proto, "..", monkeypatch, app)
    assert titles(proto) == ["Examples", "Documents"]

    tap(proto, "Examples", monkeypatch, app)
    assert proto.category == "Examples" and proto.subfolder == Path()
    assert "basics" in titles(proto)


def test_folder_rows_preview_their_contents(proto: ui.Prototype) -> None:
    """Folders show what's inside rather than just "Folder"."""
    row = next(r for r in proto.script_list.data if r.title == "a")
    assert row.subtitle == "📁 1"


def test_category_icons_appear_once_downloaded(
    proto: ui.Prototype, app: toga.App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Examples and Documents use examples.png and documents.png when present."""
    icons = tmp_path / "icons"
    icons.mkdir()
    proto.icon_path = icons
    tap(proto, "..", monkeypatch, app)
    assert all(row.icon is None for row in proto.script_list.data)

    for name in ("examples.png", "documents.png"):
        shutil.copy(ICONS / "list.png", icons / name)
    proto.reload_menu(proto.script_list)
    assert all(isinstance(row.icon, toga.Image) for row in proto.script_list.data)


def test_script_rows_show_docstrings(proto: ui.Prototype) -> None:
    """A script's docstring is its subtitle (#49)."""
    row = next(r for r in proto.script_list.data if r.title == "top")
    assert row.subtitle == "At the top."


def test_kind_icons_appear_once_downloaded(proto: ui.Prototype, tmp_path: Path) -> None:
    """Folder, ".." and script rows have no icon until the icon file exists (#50)."""
    # Start from an empty icons folder; the bundled one may already have them
    icons = tmp_path / "icons"
    icons.mkdir()
    proto.icon_path = icons
    proto.subfolder = Path("a")  # so the ".." row is listed too
    proto.reload_menu(proto.script_list)
    assert titles(proto) == ["..", "b"]
    assert all(row.icon is None for row in proto.script_list.data)

    for name in ("folder.png", "file-code.png", "arrow-small-left.png"):
        shutil.copy(ICONS / "list.png", icons / name)
    proto.reload_menu(proto.script_list)
    assert all(isinstance(row.icon, toga.Image) for row in proto.script_list.data)

    # A script row too
    proto.subfolder = Path()
    proto.reload_menu(proto.script_list)
    assert isinstance(proto.script_list.data[-1].icon, toga.Image)  # "top"


# ---------------------------------------------------------------------------
# Help and About (#34)
# ---------------------------------------------------------------------------


def test_help_about_switch(
    proto: ui.Prototype, monkeypatch: pytest.MonkeyPatch
) -> None:
    """About shows app sections, not packages; Help comes back; Share is iOS-only."""
    pages: list[str] = []
    monkeypatch.setattr(
        proto.help_view._impl, "set_content", lambda root, html: pages.append(html)
    )
    proto.help_selection.selection.value = "About"
    proto.show_help_page()
    sections = re.findall(r"<h2>(.*?)</h2>", pages[-1])
    assert [s.split(" (")[0] for s in sections] == [
        "App",
        "Python",
        "Paths",
        "Packages",
    ]
    assert "Setup → Packages" in pages[-1] and "Bundled packages" not in pages[-1]
    assert proto.about_share.style.visibility == "hidden"  # not iOS

    proto.help_selection.selection.value = "Help"
    proto.show_help_page()
    assert "Bundled packages" not in pages[-1]


# ---------------------------------------------------------------------------
# Running with dependencies (#33)
# ---------------------------------------------------------------------------


def fake_installer(
    events: list[tuple[str, str]], p: ui.Prototype, fail: bool
) -> Callable[..., Coroutine[Any, Any, None]]:
    """A stand-in for resolve_and_install_async that records the UI state."""

    async def install(
        requirements: list[str],
        target: Path,
        on_progress: Callable[[str], None] | None = None,
        **kwargs: object,
    ) -> None:
        events.append(("install starts on", p.tabs.current_tab.text))
        assert on_progress is not None
        on_progress("Downloading lib 2.0")
        events.append(("status", p.script_activity.text.text))
        if fail:
            raise piplike.DependencyError("no such package")

    return install


def test_install_happens_on_script_tab_and_errors_show_over_it(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Progress shows on Script; a failure's dialog appears there, then List."""
    (docs / "needs_dep.py").write_text(
        '"""Needs a dependency."""\n'
        "# /// script\n"
        '# dependencies = ["not-there"]\n'
        "# ///\n"
    )
    proto.reload_menu(proto.script_list)
    events: list[tuple[str, str]] = []
    monkeypatch.setattr(
        piplike, "resolve_and_install_async", fake_installer(events, proto, fail=True)
    )
    proto.tabs.current_tab = "List"

    tap(proto, "needs_dep", monkeypatch, app)

    assert events == [
        ("install starts on", "Script"),
        ("status", "Downloading lib 2.0"),
    ]
    # The dialog is shown over the Script tab, with the failure in the status line
    assert proto.dialogs == [  # type: ignore[attr-defined]
        ("Dependency Error", "no such package", "Script", "Dependency install failed")
    ]
    # Then, with no output, the run ends back on the list
    assert proto.tabs.current_tab.text == "List"


# ---------------------------------------------------------------------------
# Splash in the Script view
# ---------------------------------------------------------------------------


def splash_during_install(
    proto: ui.Prototype, app: toga.App, title: str, monkeypatch: pytest.MonkeyPatch
) -> object:
    """Tap `title` and return the Script view's splash image while it installs."""
    seen: list[object] = []

    async def install(*args: object, **kwargs: object) -> None:
        seen.append(proto.splash.image)
        raise piplike.DependencyError("stop after recording")

    monkeypatch.setattr(piplike, "resolve_and_install_async", install)
    tap(proto, title, monkeypatch, app)
    return seen[0]


def test_default_icons_are_not_used_as_a_splash(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A row showing a 24x24 default icon gets no stretched splash in Script."""
    icons = tmp_path / "icons"
    icons.mkdir()
    shutil.copy(ICONS / "list.png", icons / "file-code.png")
    proto.icon_path = icons
    (docs / "plain.py").write_text(
        '"""Plain."""\n# /// script\n# dependencies = ["x"]\n# ///\n'
    )
    proto.reload_menu(proto.script_list)
    row = next(r for r in proto.script_list.data if r.title == "plain")
    assert isinstance(row.icon, toga.Image)  # the list still shows the default

    assert splash_during_install(proto, app, "plain", monkeypatch) is None


def test_own_icon_is_used_as_a_splash(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A prototype that sets its own icon still gets it as the splash."""
    shutil.copy(ICONS / "eye.png", docs / "me.png")
    (docs / "branded.py").write_text(
        '"""Branded."""\n'
        "# /// script\n"
        '# dependencies = ["x"]\n'
        "# [tool.stub_launcher]\n"
        '# icon = "me.png"\n'
        "# ///\n"
    )
    proto.reload_menu(proto.script_list)

    splash = splash_during_install(proto, app, "branded", monkeypatch)
    assert isinstance(splash, toga.Image)
