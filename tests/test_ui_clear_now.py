"""Clear Now: emptying the log from the Logs tab, in place (#200).

Skipped where toga_dummy isn't installed, such as on device.
"""

import io
import os
from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import logfile, ui
from tests.support_ui import run


@pytest.fixture
def log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> logfile.LogRedirector:
    """A redirector with 2 KB of history, made the app's current one."""
    redirector = logfile.LogRedirector(tmp_path / "app.log", terminal=io.StringIO())
    redirector.write("x" * 2047 + "\n")
    redirector.flush()
    monkeypatch.setattr(logfile, "_current", redirector)
    return redirector


class Dialogs:
    """Stand-ins for the confirmation and the message, recording what was said."""

    def __init__(self, proto: ui.Prototype, monkeypatch: pytest.MonkeyPatch) -> None:
        self.asked: list[tuple[str, str]] = []
        self.told: list[tuple[str | None, str]] = []
        self.answer = True

        async def confirm(text: str, title: str) -> bool:
            self.asked.append((title, text))
            return self.answer

        async def info(text: str, title: str | None = None) -> None:
            self.told.append((title, text))

        monkeypatch.setattr(proto, "confirm", confirm)
        monkeypatch.setattr(proto, "info", info)


def buttons(widgets: list[toga.Widget]) -> list[toga.Button]:
    """Every button in `widgets`, however deeply nested."""
    found: list[toga.Button] = []

    def walk(widget: toga.Widget) -> None:
        if isinstance(widget, toga.Button):
            found.append(widget)
        for child in widget.children:
            walk(child)

    for widget in widgets:
        walk(widget)
    return found


def clear_button(proto: ui.Prototype) -> toga.Button:
    """The Logs tab's Clear Now button."""
    logs = next(item for item in proto.tabs.content if item.text == "Logs")
    return next(b for b in buttons([logs.content]) if b.text == ui.LOG_CLEAR)


def test_clear_now_is_on_the_logs_tab_and_always_enabled(proto: ui.Prototype) -> None:
    """Beside Reload; the Preserve Logs switch never disables it."""
    logs = next(item for item in proto.tabs.content if item.text == "Logs")
    assert [b.text for b in buttons([logs.content])] == [
        ui.LOG_RELOAD,
        ui.LOG_BOTTOM,
        ui.LOG_CLEAR,
    ]
    assert clear_button(proto).enabled is True
    assert not hasattr(proto, "clear_logs")
    assert ui.LOG_CLEAR not in [b.text for b in buttons(proto.setup_sections())]


def test_clearing_empties_the_log_and_the_tab_and_logging_goes_on(
    proto: ui.Prototype,
    app: toga.App,
    config: Path,
    log: logfile.LogRedirector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After confirming: an empty file and tab, a message, later output logged."""
    dialogs = Dialogs(proto, monkeypatch)
    proto.log_text.value = "old log text"
    proto.set_preserve_logs(True)
    run(app, proto.handle_clear_now(clear_button(proto)))
    assert dialogs.asked and "2.0 KB" in dialogs.asked[0][1]
    assert log.log_path.read_text() == "" and proto.log_text.value == ""
    assert dialogs.told[0][0] == "Log cleared" and "2.0 KB freed" in dialogs.told[0][1]
    log.write("still logging\n")
    log.flush()
    assert log.log_path.read_text() == "still logging\n"


def test_declining_keeps_the_log(
    proto: ui.Prototype,
    app: toga.App,
    config: Path,
    log: logfile.LogRedirector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No means nothing is deleted and nothing is said."""
    dialogs = Dialogs(proto, monkeypatch)
    dialogs.answer = False
    proto.log_text.value = "kept"
    run(app, proto.handle_clear_now(clear_button(proto)))
    assert log.size() == 2048 and proto.log_text.value == "kept"
    assert dialogs.told == []


@pytest.mark.parametrize("preserve", [True, False])
def test_the_truncation_itself_does_not_depend_on_the_switch(
    proto: ui.Prototype,
    app: toga.App,
    config: Path,
    log: logfile.LogRedirector,
    monkeypatch: pytest.MonkeyPatch,
    preserve: bool,
) -> None:
    """Clearing is the same with the switch on or off."""
    Dialogs(proto, monkeypatch)
    proto.set_preserve_logs(preserve)
    run(app, proto.handle_clear_now(clear_button(proto)))
    assert log.log_path.read_text() == ""


def test_with_no_log_file_it_says_so(
    proto: ui.Prototype,
    app: toga.App,
    config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Development runs and tests have no redirector."""
    dialogs = Dialogs(proto, monkeypatch)
    monkeypatch.setattr(logfile, "_current", None)
    run(app, proto.handle_clear_now(clear_button(proto)))
    assert dialogs.asked == [] and "no log file" in dialogs.told[0][1]
