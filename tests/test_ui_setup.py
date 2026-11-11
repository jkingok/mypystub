"""UI tests for the Setup tab and for web views not reloading the page they show.

Skipped where toga_dummy isn't installed, such as on device.
"""

import os
from pathlib import Path

import pytest
from packaging.version import Version

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import piplike, setup_pages, ui
from tests.support_ui import (
    run,
)

# ---------------------------------------------------------------------------
# Setup view: cache, package updates, health (#77)
# ---------------------------------------------------------------------------


@pytest.fixture
def site(proto: ui.Prototype, tmp_path: Path) -> Path:
    """A user site-packages folder, in a temp cache, holding one package."""
    proto.cache_path = tmp_path / "cache"
    site = proto.site_packages
    dist = site / "humanize-4.10.0.dist-info"
    dist.mkdir(parents=True)
    (dist / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: humanize\nVersion: 4.10.0\n"
    )
    (site / "humanize.py").write_text("X = 1\n")
    return site


def answer_dialogs(
    proto: ui.Prototype, monkeypatch: pytest.MonkeyPatch, answer: bool
) -> list[str]:
    """Answer every confirmation with `answer`, recording the questions."""
    asked: list[str] = []

    async def confirm(text: str, title: str) -> bool:
        asked.append(title)
        return answer

    monkeypatch.setattr(proto, "confirm", confirm)
    return asked


def test_setup_menu_opens_pages_with_back(
    proto: ui.Prototype, app: toga.App, site: Path
) -> None:
    """Each menu entry opens its page over the tabs; Back (even twice) returns."""
    tabs = app.main_window.content
    stack = proto.content_stack()
    depth = len(stack)
    for page, title in proto.SETUP_PAGES.items():
        proto.open_setup_page(page)
        assert app.main_window.title == title
        assert app.main_window.content is not tabs
        assert len(stack) == depth + 1
        assert proto.setup_view.parent is not None
        proto.close_setup_page()
        assert app.main_window.content is tabs
        proto.close_setup_page()  # a double tap pops nothing more
        assert app.main_window.content is tabs and len(stack) == depth
        assert proto.setup_page is None


def fake_python(client: object, current: str) -> object:
    """A python.org answer: nothing newer."""
    from mypystub import maintenance

    return maintenance.PythonStatus(Version(current), Version(current), None, None)


def test_setup_shows_user_packages(
    proto: ui.Prototype, app: toga.App, site: Path
) -> None:
    """The Packages page counts and lists user packages."""
    proto.open_setup_page("packages")
    assert proto.packages_summary.startswith("1 user package (")
    assert "humanize" in proto.setup_html and "4.10.0" in proto.setup_html
    assert setup_pages.NOT_CHECKED in proto.setup_html
    # The window's title says Packages; the page starts with its sections
    assert app.main_window.title == "Packages"
    assert "<h2>Packages</h2>" not in proto.setup_html
    assert "<h3>Aliases</h3>" in proto.setup_html  # toga and pyyaml are built in


def test_wipe_needs_confirmation(
    proto: ui.Prototype, app: toga.App, site: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Declining keeps the packages; confirming deletes them."""
    proto.open_setup_page("packages")
    asked = answer_dialogs(proto, monkeypatch, answer=False)
    run(app, proto.handle_wipe_cache(proto.update_all_button))
    assert site.exists() and asked == ["Wipe user packages"]

    answer_dialogs(proto, monkeypatch, answer=True)
    run(app, proto.handle_wipe_cache(proto.update_all_button))
    assert not site.exists()
    assert proto.packages_summary == "No user packages"
    assert "No user packages" in proto.setup_html


def test_check_and_install_updates(
    proto: ui.Prototype, app: toga.App, site: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Found updates are listed, and Update all installs exactly those versions."""
    from mypystub import maintenance

    found = [
        maintenance.Update("humanize", Version("4.10.0"), Version("4.12.0"), False)
    ]
    monkeypatch.setattr(
        maintenance,
        "find_updates",
        lambda client, inv, **kw: [] if kw.get("critical") else found,
    )
    monkeypatch.setattr(maintenance, "check_python", fake_python)
    proto.open_setup_page("packages")
    assert not proto.update_all_button.enabled
    run(app, proto.handle_check_updates(proto.update_all_button))
    assert "4.10.0 → 4.12.0" in proto.setup_html
    assert proto.update_all_button.enabled

    installed: list[list[str]] = []

    async def install(requirements: list[str], target: Path, **kwargs: object) -> None:
        installed.append(requirements)

    monkeypatch.setattr(piplike, "resolve_and_install_async", install)
    run(app, proto.handle_update_all(proto.update_all_button))
    assert installed == [["humanize==4.12.0"]]
    assert not proto.update_all_button.enabled
    assert "Up to date" in proto.setup_html


def test_check_updates_offline_says_so(
    proto: ui.Prototype, app: toga.App, site: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no network, the page and status line explain instead of failing."""
    from mypystub import maintenance

    def offline(client: object, inventory: object, **kwargs: object) -> None:
        raise maintenance.MaintenanceError("Couldn't reach PyPI: offline")

    monkeypatch.setattr(maintenance, "find_updates", offline)
    monkeypatch.setattr(maintenance, "check_python", fake_python)
    proto.open_setup_page("packages")
    run(app, proto.handle_check_updates(proto.update_all_button))
    assert "Couldn't reach PyPI: offline" in proto.setup_activity.text.text
    assert "check: Couldn&#x27;t reach PyPI: offline" in proto.setup_html
    assert not proto.update_all_button.enabled


def test_one_check_covers_packages_and_app_health(
    proto: ui.Prototype, app: toga.App, site: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check for updates asks about user packages and the app, on one page."""
    from mypystub import maintenance

    status = maintenance.PythonStatus(
        Version("3.15.1"), Version("3.15.2"), None, Version("3.16.0b1")
    )
    monkeypatch.setattr(maintenance, "check_python", lambda client, current: status)
    monkeypatch.setattr(maintenance, "find_updates", lambda client, inv, **kw: [])
    proto.open_setup_page("packages")
    assert setup_pages.NOT_CHECKED in proto.setup_html
    run(app, proto.handle_check_updates(proto.update_all_button))
    assert "✓ Up to date" in proto.setup_html  # user packages
    assert "⚠ 1 update needs a new app build (TestFlight)" in proto.setup_html
    assert "Python 3.15.1 → 3.15.2 available" in proto.setup_html
    assert "Packages up to date" in proto.setup_activity.text.text
    assert "App: ⚠ 1 update needs" in proto.setup_activity.text.text


def test_one_failed_check_does_not_hide_the_other(
    proto: ui.Prototype, app: toga.App, site: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Offline for python.org still shows the user packages result, and says so."""
    from mypystub import maintenance

    def offline(client: object, current: str) -> None:
        raise maintenance.MaintenanceError("Couldn't reach python.org: offline")

    monkeypatch.setattr(maintenance, "check_python", offline)
    monkeypatch.setattr(maintenance, "find_updates", lambda client, inv, **kw: [])
    proto.open_setup_page("packages")
    run(app, proto.handle_check_updates(proto.update_all_button))
    assert "✓ Up to date" in proto.setup_html
    assert "check (offline?)" in proto.setup_html
    assert "reach python.org: offline" in proto.setup_html


def test_the_packages_page_shows_python_bundled_user_and_aliases(
    proto: ui.Prototype, site: Path
) -> None:
    """Everything about packages is on the one page."""
    proto.open_setup_page("packages")
    html = proto.setup_html
    assert "<h3>Python</h3>" in html and "Implementation" in html
    assert "Bundled with the app" in html and "<details>" in html
    assert "<h3>User packages</h3>" in html and "humanize" in html
    assert "<h3>Aliases</h3>" in html and "pyyaml-pure" in html
    assert "<h3>App health</h3>" in html


def test_there_is_no_separate_app_health_page(proto: ui.Prototype) -> None:
    """It was merged into Packages."""
    assert "health" not in proto.SETUP_PAGES


# ---------------------------------------------------------------------------
# Setup view: permissions (#80)
# ---------------------------------------------------------------------------


def test_setup_lists_permissions(proto: ui.Prototype) -> None:
    """Each declared permission is listed with its status."""
    proto.open_setup_page("permissions")
    for name in ("Location", "Camera", "Photo library", "Local network"):
        assert f"<td>{name}</td>" in proto.setup_html


def test_open_settings_button(
    proto: ui.Prototype, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The button opens Settings on iOS, and explains itself elsewhere."""
    from mypystub import permissions

    proto.open_setup_page("permissions")
    proto.handle_open_settings(proto.update_all_button)
    assert proto.setup_activity.text.text == "Settings couldn't be opened"

    opened: list[bool] = []
    monkeypatch.setattr(
        permissions, "open_app_settings", lambda: opened.append(True) or True
    )
    proto.handle_open_settings(proto.update_all_button)
    assert opened == [True]


# ---------------------------------------------------------------------------
# A WebView isn't reloaded with the page it already shows
# ---------------------------------------------------------------------------


def test_help_page_is_not_loaded_twice(
    proto: ui.Prototype, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Building the tabs shows Help, and selecting the tab asks again: one load."""
    loads: list[str] = []
    monkeypatch.setattr(
        proto.help_view._impl, "set_content", lambda root, html: loads.append(html)
    )
    proto.help_selection.selection.value = "Help"
    proto.show_help_page()
    proto.show_help_page()  # as tab_changed does when the tab is selected
    proto.show_help_page()
    assert len(loads) <= 1
    proto.help_selection.selection.value = "About"
    proto.show_help_page()
    proto.show_help_page()
    assert len(loads) <= 2 and "Setup → Packages" in loads[-1]
    proto.help_selection.selection.value = "Help"
    proto.show_help_page()
    assert "Setup → Packages" not in loads[-1]  # a different page does load


def test_setup_page_is_not_loaded_twice(
    proto: ui.Prototype, site: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rendering an unchanged Setup page again doesn't reload it."""
    loads: list[str] = []
    monkeypatch.setattr(
        proto.setup_view._impl, "set_content", lambda root, html: loads.append(html)
    )
    proto.open_setup_page("packages")
    first = len(loads)
    proto.render_setup_page()
    proto.render_setup_page()
    assert len(loads) == first
    proto.close_setup_page()


# The Setup menu's layout doesn't depend on timing (#109)
# ---------------------------------------------------------------------------


def menu_layout(widgets: list[toga.Widget]) -> list[tuple]:
    """What decides a Setup menu entry's layout: its type, flex and children."""

    def describe(widget: toga.Widget) -> tuple:
        return (
            type(widget).__name__,
            widget.style.flex,
            widget.style.align_items,
            tuple(describe(child) for child in widget.children),
        )

    return [describe(widget) for widget in widgets]


def test_every_menu_button_fills_its_own_row(proto: ui.Prototype) -> None:
    """Buttons sit in rows and fill them, so their width is never left to chance."""
    assert not [w for w in proto.setup_sections() if isinstance(w, toga.Button)]
    rows = [
        w
        for w in proto.setup_sections()
        if w.style.direction == "row" and len(w.children) == 1
    ]
    buttons = [row.children[0] for row in rows]
    assert all(isinstance(b, toga.Button) for b in buttons)
    assert {b.text for b in buttons} >= {"Environment ›", "Backup"}
    assert all(b.style.flex == 1 for b in buttons)


def test_new_project_field_fills_its_row(proto: ui.Prototype) -> None:
    """The name field takes the space between its label and Add button."""
    (row,) = [
        w
        for w in proto.setup_sections()
        if w.style.direction == "row"
        and any(isinstance(c, toga.TextInput) for c in w.children)
    ]
    (field,) = [c for c in row.children if isinstance(c, toga.TextInput)]
    assert field.style.flex == 1


def test_menu_is_the_same_after_a_page_and_back(proto: ui.Prototype) -> None:
    """Opening a Setup page and coming back leaves the menu's layout as it was."""
    menu = proto.setup_sections()
    before = menu_layout(menu)
    proto.open_setup_page("packages")
    proto.close_setup_page()
    assert menu_layout(menu) == before
