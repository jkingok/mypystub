"""The Script tab's Experimental Console: used when toga-console is there (#355).

A project has no switch, so the console is on automatically when toga-console
is installed, and plain output otherwise. Skipped where toga_dummy isn't installed.
"""

import os
import sys
from typing import Any

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import script_tab


class FakeConsole(toga.Box):
    """A stand-in for toga-console's Console: a box with a readonly flag."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.readonly = False
        self.cleared = 0

    def clear(self) -> None:
        self.cleared += 1


@pytest.fixture
def app() -> toga.App:
    return toga.App(
        "Console test", "org.example.console", startup=lambda app: toga.Box()
    )


def without_toga_console(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make `from toga_console import …` fail, as when it isn't installed."""
    monkeypatch.setitem(sys.modules, "toga_console", None)


def test_without_toga_console_the_plain_output_is_used(
    app: toga.App, monkeypatch: pytest.MonkeyPatch
) -> None:
    without_toga_console(monkeypatch)
    tab = script_tab.ScriptTab(app)
    tab.choose_output()
    assert tab.output.children[0] is tab.print_text
    assert tab.console_widget is None


def test_by_default_the_console_is_used_when_installed(
    app: toga.App, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(script_tab, "make_console", lambda: FakeConsole())
    tab = script_tab.ScriptTab(app)
    tab.choose_output()
    assert tab.output.children[0] is tab.console_widget
    assert tab.console_widget.cleared == 1


def test_a_switch_can_turn_the_console_off_for_the_next_run(
    app: toga.App, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(script_tab, "make_console", lambda: FakeConsole())
    wanted = {"on": True}
    tab = script_tab.ScriptTab(app, console_wanted=lambda: wanted["on"])
    tab.choose_output()
    assert tab.output.children[0] is tab.console_widget
    wanted["on"] = False
    tab.choose_output()
    assert tab.output.children[0] is tab.print_text


def test_the_console_is_made_once_and_reused(
    app: toga.App, monkeypatch: pytest.MonkeyPatch
) -> None:
    made: list[FakeConsole] = []

    def factory() -> FakeConsole:
        made.append(FakeConsole())
        return made[-1]

    monkeypatch.setattr(script_tab, "make_console", factory)
    tab = script_tab.ScriptTab(app)
    tab.choose_output()
    tab.choose_output()
    assert len(made) == 1
