"""Experimental Console: the title shows ⏳ or ⌨️, and a wait raises the keyboard (#306)."""

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("toga_dummy")
pytest.importorskip("toga_console")

import toga

from mypystub import ui
from mypystub.hooks import ConsoleStdin
from mypystub.ui_base import RUNNING, WAITING
from tests.support_ui import tap, wait_for


def test_stdin_reports_a_wait_only_when_it_waits() -> None:
    seen: list[bool] = []
    stdin = ConsoleStdin(wait_callback=seen.append)
    stdin.feed("ahead\n")
    assert stdin.readline() == "ahead\n" and seen == []  # typed ahead: no wait
    import threading

    reader = threading.Thread(target=stdin.readline)
    reader.start()
    wait_until(lambda: seen == [True])
    stdin.feed("now\n")
    reader.join(2)
    assert seen == [True, False]


def wait_until(condition: Any) -> None:
    import time

    for _ in range(200):
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("timed out")


@pytest.fixture
def console_on(proto: ui.Prototype, config: Path) -> ui.Prototype:
    proto.set_experimental_console(True)
    return proto


def start(proto: ui.Prototype, app: toga.App, docs: Path, source: str, mp) -> Any:
    (docs / "case.py").write_text(source)
    proto.reload_menu(proto.script_list)
    tap(proto, "case", mp, app)
    return proto.script_output.children[0]


def test_the_title_says_running_then_waiting_then_running(
    console_on: ui.Prototype, app: toga.App, docs: Path, monkeypatch
) -> None:
    proto = console_on
    focused: list[bool] = []
    console = start(
        proto,
        app,
        docs,
        "import time\nname = input('Name? ')\ntime.sleep(0.3)\nprint(name)\n",
        monkeypatch,
    )
    monkeypatch.setattr(console, "focus", lambda: focused.append(True))
    window = app.main_window
    wait_for(app, lambda: window.title.startswith(WAITING))
    assert proto.script_activity.style.display == "none"
    console.type("Sam\n")
    wait_for(app, lambda: window.title.startswith(RUNNING))
    # The title says it's running, so the row stays hidden for the whole run
    assert proto.script_activity.style.display == "none"
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    assert not window.title.startswith((RUNNING, WAITING))  # gone at the end
    # It comes back with how the run ended
    assert proto.script_activity.style.display == "pack"
    assert proto.script_activity.text.text == "✅ Finished"


def test_a_wait_focuses_the_console_once(
    console_on: ui.Prototype, app: toga.App, docs: Path, monkeypatch
) -> None:
    """Once per wait: dismissing the keyboard isn't undone until the next wait."""
    proto = console_on
    focused: list[int] = []
    console = start(
        proto,
        app,
        docs,
        "a = input('A? ')\nb = input('B? ')\n",
        monkeypatch,
    )
    monkeypatch.setattr(console, "focus", lambda: focused.append(1))
    wait_for(app, lambda: app.main_window.title.startswith(WAITING))
    first = len(focused)
    assert first == 1  # one focus for the first wait
    console.type("1\n")
    wait_for(app, lambda: len(focused) > first)  # the second wait focuses again
    console.type("2\n")
    wait_for(app, lambda: proto.ended_run == proto.run_id)


def test_no_prefix_once_the_run_has_taken_over(
    console_on: ui.Prototype, app: toga.App, docs: Path, monkeypatch
) -> None:
    proto = console_on
    start(
        proto,
        app,
        docs,
        "import toga\n"
        "def show():\n"
        "    w = toga.App.app.main_window\n"
        "    w.content_stack.append((w.title, w.content))\n"
        "    w.content = toga.Box()\n"
        "    w.title = 'Mine'\n"
        "toga.App.app.loop.call_soon_threadsafe(show)\n",
        monkeypatch,
    )
    window = app.main_window
    wait_for(app, lambda: window.title == "Mine")
    assert proto.run_took_over
    window.title, window.content = window.content_stack.pop()
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    assert not window.title.startswith((RUNNING, WAITING))


def test_the_normal_script_tab_has_no_prefix(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch, config: Path
) -> None:
    from tests.support_ui import run_to_end

    run_to_end(proto, app, docs, "print('x')\n", monkeypatch)
    assert proto.title_prefix == ""
