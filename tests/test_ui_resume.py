"""Looking as if the app resumed after iOS ended it (#188).

Skipped where toga_dummy isn't installed, such as on device.
"""

import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import resume, ui
from tests.support_ui import fresh_stack, run, run_to_end, tap, titles

VERSION = "1.2.3"


@pytest.fixture
def state_path(app: toga.App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep the resume file in a temp folder, and give the app a version."""
    path = tmp_path / "state" / "resume.json"
    monkeypatch.setattr(ui.Prototype, "resume_path", property(lambda self: path))
    monkeypatch.setattr(toga.App, "version", property(lambda self: VERSION))
    return path


def saved(path: Path) -> dict[str, Any]:
    """The state file, as a dictionary."""
    return json.loads(path.read_text())


def write_state(path: Path, **fields: Any) -> None:
    """Save a state for this app version."""
    resume.save(path, resume.Resume(version=VERSION, **fields))


def launch(app: toga.App, monkeypatch: pytest.MonkeyPatch) -> ui.Prototype:
    """A new launcher, as after iOS ended the app: nothing carried over."""
    p = ui.Prototype(host_app=app, on_done=lambda _: None)
    fresh_stack(p)
    app.main_window.content = p.get_content()
    monkeypatch.setattr(
        p, "clear_selection", lambda widget: widget._impl._set_value("selection", None)
    )
    p.reload_menu(p.script_list)
    return p


class Calls:
    """Stand-ins for the questions and the run, recording what they were given."""

    def __init__(self, p: ui.Prototype, monkeypatch: pytest.MonkeyPatch) -> None:
        self.asked: list[tuple[str, str]] = []
        self.ran: list[Any] = []
        self.quick_start_offered = 0
        self.answer = True

        async def ask(title: str, text: str) -> bool:
            self.asked.append((title, text))
            return self.answer

        async def run_row(row: Any) -> None:
            self.ran.append(row)

        async def offer() -> None:
            self.quick_start_offered += 1

        monkeypatch.setattr(p, "ask", ask)
        monkeypatch.setattr(p, "run_row", run_row)
        monkeypatch.setattr(p, "offer_quick_start", offer)


def test_nothing_is_saved_until_the_saved_state_has_been_read(
    proto: ui.Prototype, state_path: Path
) -> None:
    """A snapshot of the freshly built launcher mustn't overwrite what's saved."""
    proto.remember()
    assert not state_path.exists()


def test_a_first_launch_starts_saving_and_offers_the_quick_start(
    proto: ui.Prototype,
    app: toga.App,
    state_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With nothing saved there is nothing to restore."""
    calls = Calls(proto, monkeypatch)
    run(app, proto.start_session())
    assert calls.quick_start_offered == 1 and calls.asked == []
    assert saved(state_path)["category"] == "Documents"
    assert saved(state_path)["tab"] == "List"


def test_going_into_a_folder_is_saved_and_restored_on_the_next_launch(
    proto: ui.Prototype,
    app: toga.App,
    state_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The list comes back to the folder the user was in."""
    Calls(proto, monkeypatch)
    run(app, proto.start_session())
    tap(proto, "a", monkeypatch, app)
    tap(proto, "b", monkeypatch, app)
    assert saved(state_path)["folder"] == "a/b"

    again = launch(app, monkeypatch)
    Calls(again, monkeypatch)
    assert again.category is None  # a fresh launch starts at the categories
    run(app, again.start_session())
    assert (again.category, again.subfolder) == ("Documents", Path("a/b"))
    assert "deep" in titles(again)


@pytest.mark.parametrize(
    ("saved_folder", "expected"),
    [("a/b/gone/deeper", "a/b"), ("a/gone", "a"), ("gone/entirely", ""), ("../x", "")],
)
def test_a_vanished_folder_gives_its_nearest_surviving_parent(
    app: toga.App,
    docs: Path,
    state_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    saved_folder: str,
    expected: str,
) -> None:
    """Deleted or renamed in Files: go to the first parent that is still there."""
    monkeypatch.setattr(toga.App, "user_documents_dir", docs, raising=False)
    write_state(state_path, category="Documents", folder=saved_folder)
    p = launch(app, monkeypatch)
    Calls(p, monkeypatch)
    run(app, p.start_session())
    assert p.category == "Documents" and p.subfolder == Path(expected)


def test_a_different_app_version_does_not_resume(
    app: toga.App, docs: Path, state_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The app may behave differently now, so start from the top."""
    monkeypatch.setattr(toga.App, "user_documents_dir", docs, raising=False)
    resume.save(
        state_path, resume.Resume("0.9", category="Documents", folder="a", tab="Logs")
    )
    p = launch(app, monkeypatch)
    calls = Calls(p, monkeypatch)
    run(app, p.start_session())
    assert p.category is None and p.tabs.current_tab.text == "List"
    assert calls.quick_start_offered == 1
    assert saved(state_path)["version"] == VERSION  # replaced for this version


def test_a_setup_page_that_was_open_is_opened_again(
    proto: ui.Prototype,
    app: toga.App,
    state_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup: back inside the page it was in."""
    Calls(proto, monkeypatch)
    run(app, proto.start_session())
    proto.tabs.current_tab = "Setup"
    proto.open_setup_page("permissions")
    assert saved(state_path)["setup_page"] == "permissions"

    again = launch(app, monkeypatch)
    Calls(again, monkeypatch)
    run(app, again.start_session())
    assert again.setup_page == "permissions" and again.tabs.current_tab.text == "Setup"
    assert app.main_window.title == "Permissions"
    again.close_setup_page()
    assert saved(state_path)["setup_page"] is None


def test_the_help_page_that_was_showing_comes_back(
    app: toga.App, state_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Help: which of Help, What's New or About."""
    write_state(state_path, tab="Help", help_page="About")
    p = launch(app, monkeypatch)
    Calls(p, monkeypatch)
    run(app, p.start_session())
    assert p.tabs.current_tab.text == "Help"
    assert str(p.help_selection.value) == "About"


def test_an_empty_script_tab_returns_to_the_list(
    app: toga.App, state_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Script (and Log) content isn't restored, so an empty Script tab is no use."""
    write_state(state_path, tab="Script")
    p = launch(app, monkeypatch)
    Calls(p, monkeypatch)
    run(app, p.start_session())
    assert p.tabs.current_tab.text == "List"


def test_a_start_that_chose_its_own_tab_does_not_resume(
    app: toga.App, docs: Path, state_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A new user or a new version opens on Help: that wins over saved state."""
    monkeypatch.setattr(toga.App, "user_documents_dir", docs, raising=False)
    write_state(state_path, category="Documents", folder="a")
    p = launch(app, monkeypatch)
    calls = Calls(p, monkeypatch)
    run(app, p.start_session(allow_resume=False))
    assert p.category is None and calls.quick_start_offered == 1
    assert saved(state_path)["category"] is None  # overwritten with where it is now


def test_a_script_that_was_running_is_offered_again_once(
    app: toga.App, docs: Path, state_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The app was ended mid-run: ask, run it if yes, and never ask twice."""
    monkeypatch.setattr(toga.App, "user_documents_dir", docs, raising=False)
    write_state(
        state_path,
        category="Documents",
        running="Documents/top.py",
        running_title="top",
    )
    p = launch(app, monkeypatch)
    calls = Calls(p, monkeypatch)
    run(app, p.start_session())
    assert len(calls.asked) == 1 and "top was running" in calls.asked[0][1]
    assert [r.title for r in calls.ran] == ["top"]
    assert calls.quick_start_offered == 0  # one question at launch is enough
    assert saved(state_path)["running"] is None

    again = launch(app, monkeypatch)  # if it ends again before running, no loop
    more = Calls(again, monkeypatch)
    run(app, again.start_session())
    assert more.asked == [] and more.ran == [] and more.quick_start_offered == 1


def test_declining_the_rerun_runs_nothing(
    app: toga.App, docs: Path, state_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No means no; the Quick Start isn't asked straight after."""
    monkeypatch.setattr(toga.App, "user_documents_dir", docs, raising=False)
    write_state(state_path, running="Documents/top.py", running_title="top")
    p = launch(app, monkeypatch)
    calls = Calls(p, monkeypatch)
    calls.answer = False
    run(app, p.start_session())
    assert len(calls.asked) == 1 and calls.ran == [] and calls.quick_start_offered == 0


def test_a_script_that_has_gone_is_not_offered(
    app: toga.App, docs: Path, state_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing to run: no question, and the Quick Start question follows."""
    monkeypatch.setattr(toga.App, "user_documents_dir", docs, raising=False)
    write_state(state_path, running="Documents/deleted.py", running_title="deleted")
    p = launch(app, monkeypatch)
    calls = Calls(p, monkeypatch)
    run(app, p.start_session())
    assert calls.asked == [] and calls.quick_start_offered == 1


def test_starting_a_run_marks_it(
    proto: ui.Prototype,
    app: toga.App,
    state_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mark is what survives if iOS ends the app during the run."""

    async def no_offer() -> None:
        pass

    monkeypatch.setattr(proto, "offer_quick_start", no_offer)
    run(app, proto.start_session())
    started: list[Any] = []
    monkeypatch.setattr(proto, "start", lambda context: started.append(context))
    target = next(r for r in proto.script_list.data if r.title == "top")
    run(app, proto.run_row(target))
    assert saved(state_path)["running"] == "Documents/top.py"
    assert saved(state_path)["running_title"] == "top"


def test_ending_a_run_clears_the_mark(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    state_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A run that ends, normally or not, leaves nothing to offer again."""

    async def no_offer() -> None:
        pass

    monkeypatch.setattr(proto, "offer_quick_start", no_offer)
    run(app, proto.start_session())
    run_to_end(proto, app, docs, "x = 1\n", monkeypatch)
    assert saved(state_path)["running"] is None
    assert proto.resume_running is None


def test_the_off_switch_stops_saving_and_forgets(
    proto: ui.Prototype,
    app: toga.App,
    config: Path,
    state_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Off: nothing saved, nothing restored, and what was saved is deleted."""
    Calls(proto, monkeypatch)
    run(app, proto.start_session())
    assert state_path.exists() and proto.resume_enabled
    proto.set_resume_enabled(False)
    assert not state_path.exists() and not proto.resume_enabled
    tap(proto, "a", monkeypatch, app)
    assert not state_path.exists()
    proto.set_resume_enabled(True)
    assert saved(state_path)["folder"] == "a"


def test_with_resume_off_a_saved_state_is_ignored(
    app: toga.App,
    docs: Path,
    config: Path,
    state_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The switch also governs what is read."""
    monkeypatch.setattr(toga.App, "user_documents_dir", docs, raising=False)
    write_state(state_path, category="Documents", folder="a")
    p = launch(app, monkeypatch)
    p.settings.set_flag("resume", False)
    Calls(p, monkeypatch)
    run(app, p.start_session())
    assert p.category is None


def test_the_switch_is_in_the_setup_menu_and_works(
    proto: ui.Prototype, config: Path, state_path: Path
) -> None:
    """A switch in the App section, on by default."""
    switches: list[toga.Switch] = []

    def walk(widget: toga.Widget) -> None:
        if isinstance(widget, toga.Switch):
            switches.append(widget)
        for child in widget.children:
            walk(child)

    for widget in proto.setup_sections():
        walk(widget)
    (switch,) = [s for s in switches if s.text == "Resume where I left off"]
    assert switch.value is True
    proto.handle_resume_toggle(SimpleNamespace(value=False))  # type: ignore[arg-type]
    assert proto.resume_enabled is False


def test_a_tab_is_saved_once_ios_has_switched_to_it(
    proto: ui.Prototype,
    app: toga.App,
    state_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """iOS reports the new tab while the old one is still current."""
    Calls(proto, monkeypatch)
    run(app, proto.start_session())
    impl = proto.tabs._impl

    def select_like_ios(index: int) -> None:
        impl.interface.on_select()
        impl._set_value("current_tab_index", index)

    monkeypatch.setattr(impl, "set_current_tab_index", select_like_ios)
    proto.tabs.current_tab = "Logs"
    run(app, asyncio.sleep(0))
    assert saved(state_path)["tab"] == "Logs"


def test_choosing_a_help_page_is_saved(
    proto: ui.Prototype,
    app: toga.App,
    state_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Picking What's New on the Help tab is remembered without a tab change."""
    Calls(proto, monkeypatch)
    run(app, proto.start_session())
    proto.tabs.current_tab = "Help"
    proto.help_selection.selection.value = "What's New"
    assert saved(state_path)["help_page"] == "What's New"


def test_the_state_is_not_kept_in_documents(app: toga.App) -> None:
    """On iOS the data folder is Documents, which Files shows to the user."""
    p = ui.Prototype(host_app=app, on_done=lambda _: None)
    assert p.resume_path.parent == Path(app.paths.config)
