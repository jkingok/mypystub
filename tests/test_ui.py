"""UI tests for the launcher, run on Toga's dummy backend (#53).

Skipped where toga_dummy isn't installed, such as on device.
"""

import asyncio
import os
import re
import shutil
from collections.abc import Callable, Coroutine
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from packaging.version import Version

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import piplike, setup_pages, ui

ICONS = Path(ui.__file__).parent / "resources" / "icons"


def fresh_stack(proto: ui.Prototype) -> None:
    """Empty the shared window's content stack before a test.

    The window is shared by the module, so pages or takeovers an earlier test
    left open would otherwise change the depths later tests wait for.
    """
    stack = proto.content_stack()
    list.clear(stack)
    stack.floor = 0


@pytest.fixture(scope="module")
def app() -> toga.App:
    """One dummy app for the module; Toga expects a single App per process."""
    app = toga.App("UI test", "org.example.uitest", startup=lambda app: toga.Box())
    app.main_window = toga.MainWindow()
    return app


@pytest.fixture
def docs(tmp_path: Path) -> Path:
    """A User documents folder with nested scripts."""
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "b" / "deep.py").write_text('"""Deep down."""\n')
    (tmp_path / "top.py").write_text('"""At the top."""\n')
    return tmp_path


@pytest.fixture
def proto(app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch) -> ui.Prototype:
    """A launcher opened on Documents, with dialogs recorded instead of shown."""
    monkeypatch.setattr(app, "user_documents_dir", docs, raising=False)
    p = ui.Prototype(host_app=app, on_done=lambda _: None)
    fresh_stack(p)
    app.main_window.content = p.get_content()
    p.dialogs = []  # type: ignore[attr-defined]

    async def record(text: str, title: str | None = None) -> None:
        p.dialogs.append(  # type: ignore[attr-defined]
            (title, text, p.tabs.current_tab.text, p.script_activity.text.text)
        )

    monkeypatch.setattr(p, "error", record)
    # On iOS, clear_selection deselects the row once it has been read; do the
    # same on the dummy backend, or every list reload re-fires on_select.
    monkeypatch.setattr(
        p, "clear_selection", lambda widget: widget._impl._set_value("selection", None)
    )
    p.reload_menu(p.script_list)
    tap(p, "Documents", monkeypatch, app)
    return p


def titles(p: ui.Prototype) -> list[str]:
    """Row titles currently in the list."""
    return [row.title for row in p.script_list.data]


def tap(
    p: ui.Prototype, title: str, monkeypatch: pytest.MonkeyPatch, app: toga.App
) -> None:
    """Select the row titled `title` on this list only, and run the handler."""
    # The dummy backend's selection is per widget, so lists from other tests
    # can't pick it up; the handler clears it once read (see the fixture).
    p.script_list._impl._set_value("selection", titles(p).index(title))
    run(app, p.handle_row_selection(p.script_list))


def run(app: toga.App, coro: Coroutine[Any, Any, Any]) -> Any:
    """Run `coro` on the app's loop."""
    return app.loop.run_until_complete(coro)


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
    assert documents.subtitle == "1 subfolder, 1 script"  # a/ and top.py
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
    assert row.subtitle == "1 subfolder"


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
    """About shows environment sections; Help comes back; Share stays iOS-only."""
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
        "Bundled packages",
        "User packages",
        "Package aliases",
    ]
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


def test_setup_shows_user_packages(proto: ui.Prototype, site: Path) -> None:
    """The Packages page counts and lists user packages."""
    proto.open_setup_page("packages")
    assert proto.packages_summary.startswith("1 user package (")
    assert "humanize" in proto.setup_html and "4.10.0" in proto.setup_html
    assert setup_pages.NOT_CHECKED in proto.setup_html


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
    monkeypatch.setattr(maintenance, "find_updates", lambda client, inv, **kw: found)
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
    proto.open_setup_page("packages")
    run(app, proto.handle_check_updates(proto.update_all_button))
    assert proto.setup_activity.text.text == "Couldn't reach PyPI: offline"
    assert "check: Couldn&#x27;t reach PyPI: offline" in proto.setup_html
    assert not proto.update_all_button.enabled


def test_health_check_states(
    proto: ui.Prototype, app: toga.App, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Health shows a summary and details; offline it says so."""
    from mypystub import maintenance

    status = maintenance.PythonStatus(
        Version("3.15.1"), Version("3.15.2"), None, Version("3.16.0b1")
    )
    monkeypatch.setattr(maintenance, "check_python", lambda client, current: status)
    monkeypatch.setattr(maintenance, "find_updates", lambda client, inv, **kw: [])
    proto.open_setup_page("health")
    assert setup_pages.NOT_CHECKED in proto.setup_html
    run(app, proto.handle_check_health(proto.update_all_button))
    assert "⚠ 1 update needs a new app build (TestFlight)" in proto.setup_html
    assert "Python 3.15.1 → 3.15.2 available" in proto.setup_html

    def offline(client: object, current: str) -> None:
        raise maintenance.MaintenanceError("Couldn't reach python.org: offline")

    monkeypatch.setattr(maintenance, "check_python", offline)
    run(app, proto.handle_check_health(proto.update_all_button))
    assert "check (offline?)" in proto.setup_html
    assert "reach python.org: offline" in proto.setup_html


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
    assert proto.setup_activity.text.text == "Settings can only be opened on iOS"

    opened: list[bool] = []
    monkeypatch.setattr(
        permissions, "open_app_settings", lambda: opened.append(True) or True
    )
    proto.handle_open_settings(proto.update_all_button)
    assert opened == [True]


# ---------------------------------------------------------------------------
# How a run ends (#64): real scripts on a live loop
# ---------------------------------------------------------------------------


def wait_for(
    app: toga.App, condition: Callable[[], bool], timeout: float = 5.0
) -> None:
    """Run the app loop until `condition()` holds."""

    async def poll() -> None:
        for _ in range(int(timeout / 0.01)):
            if condition():
                return
            await asyncio.sleep(0.01)
        raise AssertionError("timed out waiting for the run to end")

    run(app, poll())


def run_to_end(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    source: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Write `source` as a script, tap it, and wait until its run has ended."""
    (docs / "case.py").write_text(source)
    proto.reload_menu(proto.script_list)
    tap(proto, "case", monkeypatch, app)
    wait_for(app, lambda: proto.ended_run == proto.run_id)


def test_silent_script_returns_to_list(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No output and no error: back to the list."""
    run_to_end(proto, app, docs, "x = 1 + 1\n", monkeypatch)
    assert proto.tabs.current_tab.text == "List"


def test_printing_script_stays_with_finished_status(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Output keeps the Script tab open, marked Finished."""
    run_to_end(proto, app, docs, "print(1 + 1)\n", monkeypatch)
    assert proto.tabs.current_tab.text == "Script"
    assert proto.print_text.value == "2\n"
    assert proto.script_activity.text.text == "Finished"


def test_launcher_output_during_a_run_does_not_count(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Launcher prints (here, its folder scan) don't keep the Script tab open."""
    source = (
        "from pathlib import Path\n"
        "from mypystub import piplike\n"
        "piplike.scan_all_prototypes(Path('.'))  # prints 'Scanning...'\n"
    )
    run_to_end(proto, app, docs, source, monkeypatch)
    assert proto.print_text.value == ""
    assert proto.tabs.current_tab.text == "List"


def test_main_thread_callback_output_counts(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cause 2: output from a callback scheduled on the loop is shown and counted."""
    source = "import toga\ntoga.App.app.loop.call_soon_threadsafe(print, 'later')\n"
    run_to_end(proto, app, docs, source, monkeypatch)
    assert proto.print_text.value == "later\n"
    assert proto.tabs.current_tab.text == "Script"


def test_error_without_output_shows_dialog_over_script_then_list(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dialog appears over the Script tab, then the list returns."""
    run_to_end(proto, app, docs, "raise ValueError('boom')\n", monkeypatch)
    assert proto.dialogs == [  # type: ignore[attr-defined]
        ("Script Failure", "Script failed with: boom", "Script", "Failed")
    ]
    assert proto.tabs.current_tab.text == "List"


def test_takeover_ends_after_its_pop_and_extra_pops_are_ignored(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cases A and E: tabs wait for the hand-back; a double Back changes nothing."""
    source = (
        "import toga\n"
        "app = toga.App.app\n"
        "def push():\n"
        "    mw = app.main_window\n"
        "    mw.content_stack.append((mw.title, mw.content))\n"
        "    mw.content = toga.Box()\n"
        "app.loop.call_soon_threadsafe(push)\n"
    )
    (docs / "case.py").write_text(source)
    proto.reload_menu(proto.script_list)
    tap(proto, "case", monkeypatch, app)
    stack = proto.content_stack()
    wait_for(app, lambda: len(stack) == 1)
    run(app, asyncio.sleep(0.05))
    assert proto.ended_run != proto.run_id  # still taken over

    _title, content = stack.pop()  # Back
    app.main_window.content = content
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    assert proto.tabs.current_tab.text == "List"

    assert stack.pop() == (app.main_window.title, app.main_window.content)  # 2nd Back
    assert app.main_window.content is content


def test_takeover_example_hands_back_on_back(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bundled takeover example ends its run when its Back button is pressed."""
    example = (
        Path(ui.__file__).parent
        / "resources"
        / "examples"
        / "takeover"
        / "back_button.py"
    )
    (docs / "case.py").write_text(example.read_text(encoding="utf-8"))
    proto.reload_menu(proto.script_list)
    launcher = app.main_window.content
    tap(proto, "case", monkeypatch, app)
    stack = proto.content_stack()
    wait_for(app, lambda: len(stack) == 1)
    assert app.main_window.title == "Takeover"
    assert proto.ended_run != proto.run_id

    takeover = app.main_window.content
    back = next(w for w in takeover.children if isinstance(w, toga.Button))
    back._impl.simulate_press()
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    assert app.main_window.content is launcher
    assert proto.tabs.current_tab.text == "Script"  # it printed a line
    assert "Took over the screen" in proto.print_text.value

    back._impl.simulate_press()  # a double tap changes nothing
    run(app, asyncio.sleep(0.05))
    assert app.main_window.content is launcher


def test_stale_run_end_is_ignored(proto: ui.Prototype) -> None:
    """Case G: an old run finishing late doesn't touch the current run's UI."""
    from mypystub import runner

    proto.run_id = 2
    proto.tabs.current_tab = "Script"
    context = runner.RunContext(
        runner.target_for(Path(__file__), Path(__file__).parent)
    )
    proto.finish_run(context, None, run_id=1)
    assert proto.tabs.current_tab.text == "Script"
    assert proto.ended_run != 1


def test_installs_use_configured_and_script_aliases(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """launcher.toml aliases and the script's own are passed to the installer."""
    (docs / "aliased.py").write_text(
        '"""Aliased."""\n'
        "# /// script\n"
        '# dependencies = ["fast"]\n'
        "# [tool.stub_launcher.aliases]\n"
        '# fast = { kind = "substitute", target = "fast-pure" }\n'
        "# ///\n"
    )
    configured = {"slow": piplike.Alias("substitute", "slow-pure")}
    monkeypatch.setattr(proto, "configured_aliases", lambda: configured)
    seen: list[object] = []

    async def install(*args: object, **kwargs: object) -> None:
        seen.append(kwargs.get("aliases"))
        raise piplike.DependencyError("stop")

    monkeypatch.setattr(piplike, "resolve_and_install_async", install)
    proto.reload_menu(proto.script_list)
    tap(proto, "aliased", monkeypatch, app)
    assert seen == [
        {
            "slow": piplike.Alias("substitute", "slow-pure"),
            "fast": piplike.Alias("substitute", "fast-pure"),
        }
    ]


def test_nested_takeover_example_ends_back_at_the_launcher(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two levels deep: the run ends only when both screens are handed back."""
    example = (
        Path(ui.__file__).parent
        / "resources"
        / "examples"
        / "takeover"
        / "nested_takeover.py"
    )
    (docs / "case.py").write_text(example.read_text(encoding="utf-8"))
    proto.reload_menu(proto.script_list)
    launcher = app.main_window.content
    tap(proto, "case", monkeypatch, app)
    stack = proto.content_stack()
    wait_for(app, lambda: len(stack) == 1)

    def press(label: str) -> None:
        content = app.main_window.content
        button = next(
            w
            for w in content.children
            if isinstance(w, toga.Button) and w.text == label
        )
        button._impl.simulate_press()

    press("Deeper")
    wait_for(app, lambda: len(stack) == 2)
    assert app.main_window.title == "Level 2"

    press("Back")
    wait_for(app, lambda: len(stack) == 1)
    run(app, asyncio.sleep(0.05))
    assert proto.ended_run != proto.run_id  # still one level in

    press("Back")
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    assert app.main_window.content is launcher


# ---------------------------------------------------------------------------
# iPad tab row (#112)
# ---------------------------------------------------------------------------


def ipad_tabs(app: toga.App, icons: Path) -> ui.NotAnOptionContainer:
    """The iPad tab row, with two tabs whose icons exist and one without."""
    return ui.NotAnOptionContainer(
        content=[
            ("List", toga.Box(), icons / "list.png"),
            ("Script", toga.Box(), icons / "eye.png"),
            ("Help", toga.Box(), icons / "missing.png"),
        ]
    )


def test_ipad_tabs_show_which_is_selected(app: toga.App) -> None:
    """The current tab is bold in the accent colour; the others are grey."""
    tabs = ipad_tabs(app, ICONS)
    styles = {b.text: (b.style.font_weight, b.style.color) for b in tabs.buttons}
    assert styles["List"] == ("bold", None)  # Toga's default: the accent colour
    assert styles["Script"][0] == "normal" and styles["Script"][1] is not None
    tabs.current_tab = "Script"
    assert tabs.current_tab.text == "Script"
    styles = {b.text: b.style.font_weight for b in tabs.buttons}
    assert styles == {"List": "normal", "Script": "bold", "Help": "normal"}


def test_ipad_tabs_have_their_icons(app: toga.App) -> None:
    """Each tab shows the icon passed for it; a missing file shows none."""
    tabs = ipad_tabs(app, ICONS)
    assert set(tabs.icons) == {"List", "Script"}
    assert all(isinstance(icon, toga.Icon) for icon in tabs.icons.values())
    assert [b.text for b in tabs.buttons] == ["List", "Script", "Help"]


def test_ipad_tabs_press_selects_and_reports(app: toga.App) -> None:
    """Pressing a tab swaps in its content and calls on_select."""
    selected: list[str] = []
    content = toga.Box()
    tabs = ui.NotAnOptionContainer(
        content=[("List", toga.Box(), ICONS / "list.png"), ("Help", content, None)],
        on_select=lambda widget: selected.append(widget.current_tab.text),
    )
    tabs.buttons[1]._impl.simulate_press()
    assert selected[-1] == "Help"
    assert tabs.children[0] is content


def test_ipad_tab_row_clears_the_resize_handle(app: toga.App) -> None:
    """The row keeps its last tab clear of the window's corner grip."""
    tabs = ipad_tabs(app, ICONS)
    assert tabs.tab_row.style.margin_right >= 20
    assert tabs.tab_row.style.margin_bottom > 0


# Swipe actions: Info and Setup (#59)
# ---------------------------------------------------------------------------


@pytest.fixture
def config(
    proto: ui.Prototype, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point the launcher's settings at a fresh launcher.toml for this test."""
    settings = proto.settings
    path = tmp_path / "launcher.toml"
    shutil.copy(settings.config_defaults, path)
    monkeypatch.setattr(settings, "config_file", path)
    settings.config_doc = settings._load()
    return path


@pytest.fixture
def messages(proto: ui.Prototype, monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """Info dialogs and yes/no questions, recorded instead of shown."""
    shown: list[tuple] = []

    async def info(text: str, title: str | None = None) -> None:
        shown.append((title, text))

    monkeypatch.setattr(proto, "info", info)
    return shown


def row(p: ui.Prototype, title: str) -> Any:
    """The list row titled `title`."""
    return next(r for r in p.script_list.data if r.title == title)


def press(app: toga.App, button: toga.Button) -> None:
    """Press a button and let any async handler finish."""
    button._impl.simulate_press()
    run(app, asyncio.sleep(0.01))


def select(form_list: toga.DetailedList, handler: Callable, index: int) -> None:
    """Tap row `index` of one of the form's lists."""
    form_list._impl._set_value("selection", index)
    handler(form_list)


def editor_fields(app: toga.App) -> list[toga.TextInput]:
    """The text fields on the editor screen that's showing."""
    content = app.main_window.content
    return [
        w.children[0]
        for w in content.children
        if w.children and isinstance(w.children[0], toga.TextInput)
    ]


def editor_save(app: toga.App) -> toga.Button:
    """The editor screen's Done button."""
    return app.main_window.content.children[-1].children[-1]


def editor_cancel(app: toga.App) -> toga.Button:
    """The editor screen's Cancel button."""
    return app.main_window.content.children[-1].children[0]


def test_launcher_list_has_info_and_run_with_swipes(proto: ui.Prototype) -> None:
    """Swipe left is Info and swipe right is Setup, on every row."""
    assert proto.script_list._primary_action == "Info"
    assert proto.script_list._secondary_action == "Setup"


def test_swipes_on_rows_that_cannot_run_say_why(
    proto: ui.Prototype, app: toga.App, messages: list[tuple]
) -> None:
    """Folders and ".." explain, by name, why there's nothing to show or run."""
    proto.handle_run_with(proto.script_list, row=row(proto, "a"))
    run(app, asyncio.sleep(0.01))
    assert messages[-1] == (
        "a",
        (
            "a is a folder, so there's nothing to run. Open it and swipe a script "
            "or project inside."
        ),
    )
    run(app, proto.show_info(row(proto, "a")))
    assert messages[-1] == (
        "a",
        "a has no README to show. It holds 1 subfolder. Add a README.md to describe it.",
    )
    run(app, proto.show_info(row(proto, "..")))
    assert messages[-1][1] == (
        "This row goes back to the categories, so there's nothing to describe."
    )
    run(app, proto.run_with(row(proto, "..")))
    assert messages[-1][1] == (
        "This row goes back to the categories, so there's nothing to run."
    )


def test_up_rows_name_the_folder_they_lead_to(
    proto: ui.Prototype, app: toga.App, messages: list[tuple]
) -> None:
    """Deeper down, ".." names its destination."""
    proto.subfolder = Path("a/b")
    proto.reload_menu(proto.script_list)
    run(app, proto.run_with(row(proto, "..")))
    assert (
        messages[-1][1]
        == "This row goes back to Documents/a, so there's nothing to run."
    )


def test_category_swipes(
    proto: ui.Prototype, app: toga.App, messages: list[tuple]
) -> None:
    """Categories can't run; Examples has a README, Documents here has none."""
    proto.show_category(None)
    proto.reload_menu(proto.script_list)
    run(app, proto.run_with(row(proto, "Documents")))
    assert messages[-1][1].startswith("Documents holds your own scripts and projects.")
    run(app, proto.show_info(row(proto, "Documents")))
    assert "Documents has no README to show." in messages[-1][1]

    tabs = app.main_window.content
    run(app, proto.show_info(row(proto, "Examples")))
    assert app.main_window.title == "Examples"
    assert "<h1>Examples</h1>" in proto.readme_page
    proto.pop_screen()
    assert app.main_window.content is tabs


def test_folder_readme_is_shown_safely(
    proto: ui.Prototype, app: toga.App, docs: Path, messages: list[tuple]
) -> None:
    """A folder's README opens on its own screen, without its raw HTML."""
    (docs / "a" / "README.md").write_text("# About a\n\n<script>alert(1)</script>\n")
    tabs = app.main_window.content
    run(app, proto.show_info(row(proto, "a")))
    assert messages == []
    assert app.main_window.title == "a"
    page = proto.readme_page
    assert "<h1>About a</h1>" in page and "<script>alert" not in page
    assert proto.open_external(proto.readme_view, "about:blank") is True
    proto.pop_screen()
    proto.pop_screen()  # a double tap pops nothing more
    assert app.main_window.content is tabs


def test_script_info_page(
    proto: ui.Prototype, app: toga.App, messages: list[tuple]
) -> None:
    """Info on a script opens its page: docstring, dependencies, source."""
    tabs = app.main_window.content
    run(app, proto.show_info(row(proto, "top")))
    assert messages == []
    assert app.main_window.title == "top"
    page = proto.readme_page
    assert "<h1>top</h1>" in page and "<p>At the top.</p>" in page
    assert "<h2>Source</h2>" in page and "top.py, 1 line." in page
    assert str(proto.data_path) not in page  # no local paths
    proto.pop_screen()
    assert app.main_window.content is tabs


def test_run_with_form_edits_arguments(
    proto: ui.Prototype, app: toga.App, config: Path
) -> None:
    """Add, select, move, edit and delete arguments; buttons follow the selection."""
    tabs = app.main_window.content
    form = proto.open_run_with(row(proto, "top"))
    assert app.main_window.title == "Setup · top"
    assert not form.arg_buttons["edit"].enabled
    for value in ("--name", "Ada", "x"):
        form.add_arg()
        (field,) = editor_fields(app)
        field.value = value
        press(app, editor_save(app))
    assert form.args == ["--name", "Ada", "x"]
    assert form.arg_index == 2  # the new row is selected
    assert [r.subtitle for r in form.args_list.data] == [
        "Argument 1",
        "Argument 2",
        "Argument 3",
    ]

    select(form.args_list, form._arg_selected, 0)
    enabled = {w: b.enabled for w, b in form.move_buttons.items()}
    assert enabled == {"top": False, "up": False, "down": True, "bottom": True}
    press(app, form.move_buttons["bottom"])
    assert form.args == ["Ada", "x", "--name"] and form.arg_index == 2
    press(app, form.move_buttons["up"])
    assert form.args == ["Ada", "--name", "x"] and form.arg_index == 1
    press(app, form.move_buttons["top"])
    assert form.args == ["--name", "Ada", "x"] and form.arg_index == 0

    select(form.args_list, form._arg_selected, 1)
    press(app, form.arg_buttons["edit"])
    (field,) = editor_fields(app)
    assert field.value == "Ada"
    field.value = "Ada Lovelace"
    press(app, editor_save(app))
    press(app, form.arg_buttons["delete"])
    assert form.args == ["--name", "x"] and form.arg_index is None
    assert not form.arg_buttons["delete"].enabled

    form.done()
    assert app.main_window.content is tabs
    # Every change was saved as it was made
    assert proto.settings.get_run_with("Documents/top.py").args == ["--name", "x"]


def test_run_with_form_environment_is_sorted_and_inherits_setup(
    proto: ui.Prototype, app: toga.App, config: Path
) -> None:
    """Variables stay A–Z; Setup's show as inherited and can be overridden."""
    proto.settings.set_environment({"GREETING": "Hello"})
    form = proto.open_run_with(row(proto, "top"))
    assert [(r.title, r.subtitle) for r in form.env_list.data] == [
        ("GREETING", "Hello · from Setup")
    ]
    select(form.env_list, form._env_selected, 0)
    assert form.env_buttons["edit"].enabled
    assert not form.env_buttons["delete"].enabled  # it's set in Setup
    assert "set in Setup" in form.env_note.text

    press(app, form.env_buttons["edit"])  # override it here
    name, value = editor_fields(app)
    assert (name.value, value.value) == ("GREETING", "Hello")
    value.value = "Hi"
    press(app, editor_save(app))
    for new_name in ("zed", "Alpha"):
        form.add_env()
        name, value = editor_fields(app)
        name.value, value.value = new_name, ""
        press(app, editor_save(app))
    assert [(r.title, r.subtitle) for r in form.env_list.data] == [
        ("Alpha", "(empty)"),
        ("GREETING", "Hi"),
        ("zed", "(empty)"),
    ]

    select(form.env_list, form._env_selected, 1)
    assert "overrides an inherited value" in form.env_note.text
    press(app, form.env_buttons["delete"])  # the inherited value is back
    assert form.env == {"zed": "", "Alpha": ""}
    assert form.env_list.data[1].subtitle == "Hello · from Setup"


def test_run_with_form_refuses_bad_names(
    proto: ui.Prototype, app: toga.App, config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bad names keep the editor open; replacing a name asks first."""
    told: list[tuple[str, str]] = []
    answers: list[bool] = [False]

    async def tell(title: str, text: str) -> None:
        told.append((title, text))

    async def ask(title: str, text: str) -> bool:
        return answers.pop(0)

    monkeypatch.setattr(proto, "tell", tell)
    monkeypatch.setattr(proto, "ask", ask)
    form = proto.open_run_with(row(proto, "top"))
    form.add_env()
    name, value = editor_fields(app)
    for bad in ("A=B", "MY VAR", "1ST", "my-var"):
        name.value = bad
        press(app, editor_save(app))
        assert told and told[-1][0] == "Variable name"
        assert app.main_window.title == "Add variable"  # still editing
    assert form.env == {}
    name.value, value.value = "A", "x\0y"
    press(app, editor_save(app))
    assert told[-1][0] == "Variable value" and "NUL" in told[-1][1]
    assert app.main_window.title == "Add variable"
    name.value, value.value = "A", "1"
    press(app, editor_save(app))
    assert form.env == {"A": "1"}

    form.add_env()
    name, value = editor_fields(app)
    name.value, value.value = "A", "2"
    press(app, editor_save(app))  # "Replace?" answered no
    assert form.env == {"A": "1"}
    assert app.main_window.title == "Add variable"


def test_setup_form_saves_as_you_go_and_done_never_runs(
    proto: ui.Prototype, app: toga.App, config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each change is saved straight away; Done only closes, it doesn't run."""
    runs: list[Any] = []

    async def run_row(r: Any) -> None:
        runs.append(r.title)

    monkeypatch.setattr(proto, "run_row", run_row)
    form = proto.open_run_with(row(proto, "top"))
    assert "run_with" not in config.read_text()  # opening saves nothing
    form.add_arg()
    (field,) = editor_fields(app)
    field.value = "one"
    press(app, editor_save(app))
    assert proto.settings.get_run_with("Documents/top.py").args == ["one"]
    form.add_env()
    name, value = editor_fields(app)
    name.value, value.value = "B", "2"
    press(app, editor_save(app))
    assert proto.settings.get_run_with("Documents/top.py").env == {"B": "2"}

    form.add_arg()
    (field,) = editor_fields(app)
    field.value = "abandoned"
    press(app, editor_cancel(app))  # the editor's Cancel drops the typing
    assert proto.settings.get_run_with("Documents/top.py").args == ["one"]

    form.done()
    run(app, asyncio.sleep(0.01))
    assert runs == []
    form = proto.open_run_with(row(proto, "top"))
    assert (form.args, form.env) == (["one"], {"B": "2"})
    form.done()


def test_tap_runs_with_saved_arguments_and_inherited_environment(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tap passes the saved argv, and Setup's variables under the script's own."""
    from mypystub.run_settings import RunSettings

    proto.settings.set_environment({"GREETING": "Hello", "WHO": "world"})
    proto.settings.set_run_with(
        "Documents/case.py", RunSettings(["--loud", "two words"], {"WHO": "Ada"})
    )
    source = (
        "import os, sys\n"
        "print(sys.argv[1:])\n"
        "print(os.environ['GREETING'], os.environ['WHO'])\n"
    )
    run_to_end(proto, app, docs, source, monkeypatch)
    assert proto.print_text.value == "['--loud', 'two words']\nHello Ada\n"
    assert "WHO" not in os.environ  # restored after the run


def test_setup_environment_page(
    proto: ui.Prototype, app: toga.App, config: Path
) -> None:
    """The Setup tab's Environment page edits variables only, saving as it goes."""
    form = proto.open_setup_environment()
    assert not form.with_args
    assert app.main_window.title == "Environment"
    form.add_env()
    name, value = editor_fields(app)
    name.value, value.value = "GREETING", "Hello"
    press(app, editor_save(app))
    assert proto.settings.get_environment() == {"GREETING": "Hello"}
    form.done()


def test_setup_forms_have_only_done(proto: ui.Prototype, config: Path) -> None:
    """With changes saved as they're made, Done is the only button needed."""
    for form in (
        proto.open_run_with(row(proto, "top")),
        proto.open_setup_environment(),
    ):
        buttons = [
            w.text
            for w in form.content.children[-1].children
            if isinstance(w, toga.Button)
        ]
        assert buttons == ["Done"]
        form.done()


def test_run_with_toolbars_use_spaced_symbols(
    proto: ui.Prototype, config: Path
) -> None:
    """Toolbar buttons are symbols, to fit a phone, with space between them."""
    form = proto.open_run_with(row(proto, "top"))

    def labels(box: toga.Widget) -> list[str]:
        return [w.text for w in box.children if isinstance(w, toga.Button)]

    args_header, _, _, move_row, env_header = form.content.children[:5]
    assert labels(args_header) == ["+", "✎", "⌫"]
    assert labels(env_header) == ["+", "✎", "⌫"]
    assert labels(move_row) == ["⤒", "↑", "↓", "⤓"]
    for button in args_header.children[1:] + env_header.children[1:]:
        assert button.style.margin_left > 0 and button.style.margin_right > 0
    form.done()


def test_lists_keep_their_selection_when_the_form_reappears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On iOS, a reappearing table must not clear the highlighted row."""
    from mypystub import run_with

    native_controller = SimpleNamespace(clearsSelectionOnViewWillAppear=True)
    widget = SimpleNamespace(_impl=SimpleNamespace(native_controller=native_controller))
    run_with.keep_selection(widget)  # type: ignore[arg-type]
    assert native_controller.clearsSelectionOnViewWillAppear  # not iOS: untouched
    monkeypatch.setattr(run_with.sys, "platform", "ios")
    run_with.keep_selection(widget)  # type: ignore[arg-type]
    assert native_controller.clearsSelectionOnViewWillAppear is False


# ---------------------------------------------------------------------------
# Packages with several entry points (#94)
# ---------------------------------------------------------------------------

TOOLS_PYPROJECT = """
[project]
name = "tools"
description = "Some tools"

[project.scripts]
echo = "tools.cli:echo"

[project.gui-scripts]
window = "tools.cli:echo"

[project.entry-points."tools.plugins"]
value = "tools.cli:VALUE"
"""

TOOLS_CLI = """
import os
import sys

VALUE = 42


def echo():
    print(sys.argv)
    print(os.environ.get("GREETING"), os.environ.get("WHO"), os.environ.get("LEVEL"))
"""


@pytest.fixture
def tools(docs: Path, proto: ui.Prototype) -> Path:
    """A package with console, GUI and plugin entry points in Documents."""
    project = docs / "tools"
    (project / "src" / "tools").mkdir(parents=True)
    (project / "pyproject.toml").write_text(TOOLS_PYPROJECT)
    (project / "src" / "tools" / "__init__.py").write_text("")
    (project / "src" / "tools" / "cli.py").write_text(TOOLS_CLI)
    proto.reload_menu(proto.script_list)
    return project


def test_package_opens_like_a_folder_of_entry_points(
    proto: ui.Prototype, app: toga.App, tools: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tapping the package lists its entry points; ".." goes back."""
    assert titles(proto) == ["..", "a", "tools", "top"]
    assert row(proto, "tools").kind == "package"
    tap(proto, "tools", monkeypatch, app)
    assert titles(proto) == ["..", "echo", "value", "window"]
    assert [r.subtitle for r in proto.script_list.data] == [
        "Back to Documents",
        "Console · tools.cli:echo",
        "tools.plugins · tools.cli:VALUE",
        "GUI · tools.cli:echo",
    ]
    tap(proto, "..", monkeypatch, app)
    assert titles(proto) == ["..", "a", "tools", "top"]


def test_package_and_entry_icons_are_placeholders_until_added(
    proto: ui.Prototype,
    app: toga.App,
    tools: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """boxes, terminal, window and plug icons show once their files exist."""
    icons = tmp_path / "icons"
    icons.mkdir()
    proto.icon_path = icons
    proto.reload_menu(proto.script_list)
    assert row(proto, "tools").icon is None
    tap(proto, "tools", monkeypatch, app)
    assert all(r.icon is None for r in proto.script_list.data)

    for name in ("boxes.png", "terminal.png", "window.png", "plug.png"):
        shutil.copy(ICONS / "list.png", icons / name)
    proto.reload_menu(proto.script_list)
    assert all(isinstance(r.icon, toga.Image) for r in proto.script_list.data[1:])
    proto.package_dir = None
    proto.reload_menu(proto.script_list)
    assert isinstance(row(proto, "tools").icon, toga.Image)


def test_package_info_lists_its_entry_points(
    proto: ui.Prototype,
    app: toga.App,
    tools: Path,
    messages: list[tuple],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Info on a package lists entries; on an entry it names the package."""
    run(app, proto.show_info(row(proto, "tools")))
    assert "<h2>Entry points</h2>" in proto.readme_page
    assert "<code>echo</code>: Console · <code>tools.cli:echo</code>" in (
        proto.readme_page
    )
    proto.pop_screen()
    tap(proto, "tools", monkeypatch, app)
    run(app, proto.show_info(row(proto, "echo")))
    page = proto.readme_page
    assert "An entry point of tools: <code>echo</code>: Console" in page
    assert "<h2>Entry points</h2>" not in page
    proto.pop_screen()
    run(app, proto.run_with(row(proto, "..")))
    assert (
        messages[-1][1] == "This row goes back to Documents, so there's nothing to run."
    )


def test_package_setup_sets_inherited_variables_only(
    proto: ui.Prototype, app: toga.App, tools: Path, config: Path
) -> None:
    """A package's Setup has no arguments; its variables save as they change."""
    run(app, proto.run_with(row(proto, "tools")))
    form = proto.run_with_form
    assert not form.with_args
    assert app.main_window.title == "Setup · tools"
    form.env = {"WHO": "Ada"}
    form.changed()
    form.done()
    from mypystub.run_settings import RunSettings

    assert proto.settings.get_run_with("Documents/tools") == RunSettings(
        [], {"WHO": "Ada"}
    )
    assert "args" not in proto.settings.get_table("run_with")["Documents/tools"]


def test_entry_inherits_setup_then_package_then_its_own(
    proto: ui.Prototype,
    app: toga.App,
    tools: Path,
    config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An entry point's form and run layer Setup, its package, then its own."""
    from mypystub.run_settings import RunSettings

    proto.settings.set_environment({"GREETING": "Hello", "WHO": "world", "LEVEL": "1"})
    proto.settings.set_run_with("Documents/tools", RunSettings([], {"WHO": "Ada"}))
    proto.settings.set_run_with(
        "Documents/tools:echo", RunSettings(["--loud"], {"LEVEL": "2"})
    )
    tap(proto, "tools", monkeypatch, app)
    form = proto.open_run_with(row(proto, "echo"))
    assert [(r.title, r.subtitle) for r in form.env_list.data] == [
        ("GREETING", "Hello · from Setup"),
        ("LEVEL", "2"),
        ("WHO", "Ada · from tools"),
    ]
    assert form.args == ["--loud"]
    form.done()

    tap(proto, "echo", monkeypatch, app)
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    assert proto.print_text.value == "['echo', '--loud']\nHello Ada 2\n"


def test_entry_that_cannot_run_says_why(
    proto: ui.Prototype,
    app: toga.App,
    tools: Path,
    config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-callable entry point gets a "Can't Run" dialog, not a traceback."""
    tap(proto, "tools", monkeypatch, app)
    tap(proto, "value", monkeypatch, app)
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    title, text, _, _ = proto.dialogs[-1]  # type: ignore[attr-defined]
    assert title == "Can't Run"
    assert text == "tools.cli:VALUE is an int, not something that can run."


# ---------------------------------------------------------------------------
# A run's stdout and stderr (#119)
# ---------------------------------------------------------------------------


def test_stderr_pane_appears_only_when_written_to(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stderr goes to its own pane, shown on the first write; stdout stays put."""
    assert proto.error_pane.style.display == "none"
    source = (
        "import sys\nsys.stdout.write('out\\n')\nprint('warned', file=sys.stderr)\n"
    )
    run_to_end(proto, app, docs, source, monkeypatch)
    assert proto.print_text.value == "out\n"
    assert proto.error_text.value == "warned\n"
    assert proto.error_pane.style.display == "pack"
    assert proto.error_text.style.color is not None  # the warning colour


def test_hide_lasts_until_the_next_write(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hide hides the pane; more stderr shows it again; a new run starts hidden."""
    run_to_end(proto, app, docs, "import sys\nsys.stderr.write('a\\n')\n", monkeypatch)
    proto.hide_errors()
    assert proto.error_pane.style.display == "none"
    proto.show_error_output("b\n")
    assert proto.error_pane.style.display == "pack"
    assert proto.error_text.value == "a\nb\n"

    run_to_end(proto, app, docs, "print('quiet')\n", monkeypatch)
    assert proto.error_text.value == ""
    assert proto.error_pane.style.display == "none"


def test_script_output_container_is_orientation_aware(proto: ui.Prototype) -> None:
    """Output and errors share the Script tab: stacked in portrait, side by side
    in landscape."""
    from mypystub.widgets import OrientationBox

    assert isinstance(proto.script_output, OrientationBox)
    assert proto.script_output.children == [proto.script_scroll, proto.error_pane]


def test_streams_are_restored_after_a_run(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After the run, sys.stdout and sys.stderr are the app's again."""
    import sys

    stdout, stderr = sys.stdout, sys.stderr
    run_to_end(proto, app, docs, "print('x')\n", monkeypatch)
    assert (sys.stdout, sys.stderr) == (stdout, stderr)


# ---------------------------------------------------------------------------
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
