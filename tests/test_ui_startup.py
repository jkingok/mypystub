"""UI tests for the tab the app opens on: new users, and What's New.

Skipped where toga_dummy isn't installed, such as on device.
"""

import os
from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import ui

# New users open on Help (#125)
# ---------------------------------------------------------------------------


def test_new_user_opens_on_help(
    proto: ui.Prototype, app: toga.App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no version recorded, the app opens on the Help tab."""
    monkeypatch.setattr(type(app), "version", "2026.11.3.1", raising=False)
    proto.cache_path = tmp_path / "fresh-cache"
    proto.tabs.current_tab = "List"
    assert proto.choose_start_tab() == "Help"


def test_returning_user_opens_on_the_list(
    proto: ui.Prototype, app: toga.App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With this version already recorded, the app opens on the List."""
    monkeypatch.setattr(type(app), "version", "2026.11.3.1", raising=False)
    proto.cache_path = tmp_path / "cache"
    proto.tabs.current_tab = "List"
    assert proto.choose_start_tab() == "Help"  # the first run records the version
    proto.tabs.current_tab = "List"
    assert proto.choose_start_tab() == "List"


def test_unwritable_cache_opens_on_the_list(
    proto: ui.Prototype, app: toga.App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the version can't be recorded, the app still starts."""
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setattr(type(app), "version", "2026.11.3.1", raising=False)
    proto.cache_path = blocker / "cache"
    proto.tabs.current_tab = "List"
    assert proto.choose_start_tab() == "List"  # no record possible: not a new user


# ---------------------------------------------------------------------------
# What's New (#126)
# ---------------------------------------------------------------------------


def rendered_help(proto: ui.Prototype, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Collect the pages the Help view is given."""
    pages: list[str] = []
    monkeypatch.setattr(
        proto.help_view._impl, "set_content", lambda root, html: pages.append(html)
    )
    return pages


def test_help_has_a_whats_new_entry(
    proto: ui.Prototype, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Help, What's New and About are the entries, in that order."""
    assert [str(item.value) for item in proto.help_selection.selection.items] == [
        "Help",
        "What's New",
        "About",
    ]
    (tmp_path / "changes.md").write_text("# What's New\n\n## 1.2.3.4 (2026-11-03)\n")
    (tmp_path / "help.md").write_text("# Help\n")
    proto.template_path = tmp_path
    pages = rendered_help(proto, monkeypatch)
    proto.help_selection.selection.value = "What's New"
    proto.show_help_page()
    assert "1.2.3.4 (2026-11-03)" in pages[-1] and "<h1>Help</h1>" not in pages[-1]
    assert proto.about_share.style.visibility == "hidden"


def test_whats_new_without_a_file_says_so(
    proto: ui.Prototype, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A missing changes.md shows a friendly line, not a blank page."""
    proto.template_path = tmp_path
    pages = rendered_help(proto, monkeypatch)
    proto.help_selection.selection.value = "What's New"
    proto.show_help_page()
    assert "Nothing new to report yet." in pages[-1]


def test_bundled_whats_new_file_exists() -> None:
    """The app ships a What's New file that starts with its title."""
    path = Path(ui.__file__).parent / "resources" / "templates" / "changes.md"
    assert path.read_text(encoding="utf-8").startswith("# What's New")


def test_first_open_of_a_new_version_shows_whats_new(
    proto: ui.Prototype,
    app: toga.App,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A different stored version opens Help on What's New, once."""
    from mypystub import first_run

    monkeypatch.setattr(type(app), "version", "2026.11.3.2", raising=False)
    proto.cache_path = tmp_path / "cache"
    first_run.record_version(proto.cache_path, "2026.11.3.1")
    proto.tabs.current_tab = "List"
    assert proto.choose_start_tab() == "Help"
    assert str(proto.help_selection.value) == "What's New"
    proto.help_selection.selection.value = "Help"
    proto.tabs.current_tab = "List"
    assert proto.choose_start_tab() == "List"  # recorded: shown only once


def test_a_new_user_sees_help_not_whats_new(
    proto: ui.Prototype,
    app: toga.App,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no version recorded, Help opens on the Help page itself."""
    monkeypatch.setattr(type(app), "version", "2026.11.3.2", raising=False)
    proto.cache_path = tmp_path / "fresh"
    proto.tabs.current_tab = "List"
    proto.help_selection.selection.value = "Help"
    assert proto.choose_start_tab() == "Help"
    assert str(proto.help_selection.value) == "Help"
