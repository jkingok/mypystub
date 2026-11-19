"""New on the List tab, and the new project in both of its homes (#146).

Skipped where toga_dummy isn't installed, such as on device.
"""

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("toga_dummy")

import toga

from mypystub import new_items, ui
from tests.support_ui import fresh_stack, run, tap, titles, wait_for


def test_new_is_only_offered_where_things_can_be_added(proto: ui.Prototype) -> None:
    assert proto.new_button.enabled  # the fixture has Documents open
    proto.show_category(None)
    proto.reload_menu(proto.script_list)
    assert not proto.new_button.enabled


def test_new_makes_a_script_and_shows_its_info(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown: list[Path] = []

    async def record(path: Path) -> None:
        shown.append(path)

    monkeypatch.setattr(proto, "show_info_for", record)
    run(app, proto.handle_new())
    assert proto.new_name is not None
    proto.new_name.value = "My Tool"
    run(app, proto.create_new_script())
    proto.new_details["description"].value = "Counts things"
    run(app, proto.make_new_script())
    assert (docs / "my_tool.py").exists()
    assert "My Tool: Counts things" in (docs / "my_tool.py").read_text()
    assert app.main_window.content is proto.tabs  # the New screen is gone
    assert "my_tool" in titles(proto)
    assert shown == [docs / "my_tool.py"]


def test_new_makes_a_project(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(proto, "show_info_for", lambda path: _done())
    run(app, proto.handle_new())
    proto.new_name.value = "Weather Now"  # type: ignore[union-attr]
    run(app, proto.create_new_project())
    assert set(proto.new_details) == {"description", "bundle", "author"}
    proto.new_details["bundle"].value = "au.id.someone"
    proto.new_details["author"].value = "Sam Coder"
    run(app, proto.make_new_project())
    pyproject = (docs / "weather_now" / "pyproject.toml").read_text()
    assert 'bundle = "au.id.someone"' in pyproject and "Sam Coder" in pyproject
    assert "Weather Now" in titles(proto)
    assert app.main_window.content is proto.tabs  # both screens are gone


def test_a_bad_bundle_keeps_the_details_screen(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown: list[str] = []

    async def note(message: str, title: str = "") -> None:
        shown.append(message)

    monkeypatch.setattr(proto, "info", note)
    run(app, proto.handle_new())
    proto.new_name.value = "Weather Now"  # type: ignore[union-attr]
    run(app, proto.create_new_project())
    details = app.main_window.content
    proto.new_details["bundle"].value = "not a bundle"
    run(app, proto.make_new_project())
    assert not (docs / "weather_now").exists()
    assert app.main_window.content is details and "reversed domain" in shown[0]
    proto.back_new()
    proto.cancel_new()
    assert app.main_window.content is proto.tabs


async def _done() -> None:
    return None


def test_cancel_and_an_empty_name_make_nothing(
    proto: ui.Prototype, app: toga.App, docs: Path
) -> None:
    before = sorted(p.name for p in docs.iterdir())
    run(app, proto.handle_new())
    proto.new_name.value = "  "  # type: ignore[union-attr]
    run(app, proto.create_new_script())  # refused: no details screen
    assert not proto.new_details
    proto.cancel_new()
    assert app.main_window.content is proto.tabs
    assert sorted(p.name for p in docs.iterdir()) == before


@pytest.fixture
def made(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """A new project's package, importable as `weather_now`."""
    project = new_items.create_project(tmp_path, "Weather Now")
    monkeypatch.syspath_prepend(str(project / "src"))
    for name in [n for n in sys.modules if n.startswith("weather_now")]:
        monkeypatch.delitem(sys.modules, name)
    importlib.invalidate_caches()
    yield (
        importlib.import_module("weather_now.app"),
        importlib.import_module("weather_now.bootstrap"),
    )
    for name in [n for n in sys.modules if n.startswith("weather_now")]:
        sys.modules.pop(name, None)


def settle(app: toga.App) -> None:
    run(app, __import__("asyncio").sleep(0.01))


def test_in_the_launcher_it_takes_over_with_a_back_button(
    proto: ui.Prototype, app: toga.App, made: Any
) -> None:
    """Inside MyPyStub, main() pushes the launcher and shows Back, which returns."""
    _, bootstrap = made
    fresh_stack(proto)
    window = app.main_window
    launcher = window.content
    assert bootstrap.main() is None  # an app is running: just runs the app
    settle(app)
    assert window.content is not launcher and window.title == "Weather Now"
    back = _button(window.content, "‹ Back")
    assert back.style.visibility == "visible"
    back._impl.simulate_press()
    assert window.content is launcher


def test_as_an_app_of_its_own_back_is_hidden(app: toga.App, made: Any) -> None:
    """With no content_stack (the bootstrap keeps none), Back has nowhere to go."""
    the_app, _ = made
    window = app.main_window
    saved = (window.title, window.content, getattr(window, "content_stack", None))
    try:
        if hasattr(window, "content_stack"):
            delattr(window, "content_stack")
        the_app.build(app)
        assert _button(window.content, "‹ Back").style.visibility == "hidden"
    finally:
        window.title, window.content = saved[0], saved[1]
        if saved[2] is not None:
            window.content_stack = saved[2]


def bootstrap_on(app: toga.App, bootstrap: Any) -> Any:
    """The bootstrap's run logic, on the test's app and window."""
    host = bootstrap.Bootstrap.__new__(bootstrap.Bootstrap)
    host.__dict__.update(window=app.main_window, _formal_name="Weather Now")
    type(host).loop = property(lambda self: app.loop)  # type: ignore[attr-defined]
    host.script = bootstrap.ScriptView(app, host.run_app)
    return host


def test_the_bootstrap_shows_an_error_and_offers_restart(
    app: toga.App, made: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    the_app, bootstrap = made
    saved = (app.main_window.title, app.main_window.content)
    host = bootstrap_on(app, bootstrap)

    def broken() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(the_app, "main", broken)
    try:
        host.run_app()
        wait_for(app, lambda: host.script.restart.enabled)
        assert app.main_window.content is host.script.box
        assert host.script.status.text == "Stopped with an error"
    finally:
        app.main_window.title, app.main_window.content = saved


def test_the_bootstrap_offers_restart_when_the_app_finishes(
    app: toga.App, made: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    the_app, bootstrap = made
    saved = (app.main_window.title, app.main_window.content)
    host = bootstrap_on(app, bootstrap)
    monkeypatch.setattr(the_app, "main", lambda: None)
    try:
        host.run_app()
        wait_for(app, lambda: host.script.restart.enabled)
        assert host.script.status.text == "Finished"
    finally:
        app.main_window.title, app.main_window.content = saved


def test_the_bootstrap_leaves_a_takeover_alone(app: toga.App, made: Any) -> None:
    _, bootstrap = made
    saved = (app.main_window.title, app.main_window.content)
    stack = getattr(app.main_window, "content_stack", None)
    host = bootstrap_on(app, bootstrap)
    try:
        if stack is not None:
            delattr(app.main_window, "content_stack")
        host.run_app()
        wait_for(app, lambda: app.main_window.content is not host.script.box)
        settle(app)
        assert host.script.status.text == "Running" and not host.script.restart.enabled
    finally:
        app.main_window.title, app.main_window.content = saved
        if stack is not None:
            app.main_window.content_stack = stack


def test_input_and_getpass_wait_for_the_script_view(
    app: toga.App, made: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """main()'s thread waits; Return answers; getpass() isn't echoed."""
    the_app, bootstrap = made
    window = app.main_window
    saved = (window.title, window.content)
    host = bootstrap_on(app, bootstrap)
    answers: list[str] = []

    def asks() -> None:
        answers.append(host.script.ask("Name? "))
        answers.append(host.script.ask_secret("Password: "))

    monkeypatch.setattr(the_app, "main", asks)
    view = host.script
    try:
        host.run_app()
        wait_for(app, lambda: view.question.style.visibility == "visible")
        assert view.prompt.text == "Name? "
        view.answer.value = "Sam"
        view.answered(view.answer)
        wait_for(app, lambda: view.prompt.text == "Password: ")
        assert view.secret.style.display == "pack"
        view.secret.value = "hunter2"
        view.answered(view.secret)
        wait_for(app, lambda: len(answers) == 2)
        assert answers == ["Sam", "hunter2"]
        wait_for(app, lambda: view.restart.enabled)
    finally:
        window.title, window.content = saved[0], saved[1]


def test_android_back_pops_the_apps_own_stack(app: toga.App, made: Any) -> None:
    """Back goes through content_stack when the app keeps one; else Android's."""
    _, bootstrap = made
    window = app.main_window
    saved = (window.title, window.content, getattr(window, "content_stack", None))
    host = bootstrap_on(app, bootstrap)
    earlier = toga.Box()
    try:
        window.content_stack = [("Earlier", earlier)]
        assert host.go_back() is True
        assert window.content is earlier and window.title == "Earlier"
        assert host.go_back() is False  # nothing left: Android's own Back
    finally:
        window.title, window.content = saved[0], saved[1]
        if saved[2] is not None:
            window.content_stack = saved[2]
        else:
            delattr(window, "content_stack")


def _button(widget: toga.Widget, text: str) -> toga.Button:
    pending = [widget]
    while pending:
        current = pending.pop()
        if isinstance(current, toga.Button) and current.text == text:
            return current
        pending.extend(current.children)
    raise AssertionError(f"no {text} button")


_ = tap  # the support module is imported for its dummy backend
