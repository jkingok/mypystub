"""UI tests for the launcher, run on Toga's dummy backend (#53).

Skipped where toga_dummy isn't installed, such as on device.
"""

import asyncio
import os
import re
import shutil
from collections.abc import Callable, Coroutine
from pathlib import Path
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
