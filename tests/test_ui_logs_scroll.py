"""The Logs tab goes to the newest line when it reloads, and has a jump button (#199).

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
    """A log with a few lines in it, made the app's current one."""
    redirector = logfile.LogRedirector(tmp_path / "app.log", terminal=io.StringIO())
    redirector.write("first\nsecond\nnewest\n")
    redirector.flush()
    monkeypatch.setattr(logfile, "_current", redirector)
    return redirector


@pytest.fixture
def scrolls(proto: ui.Prototype, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record the text box being scrolled to its bottom."""
    calls: list[str] = []
    monkeypatch.setattr(
        proto.log_text, "scroll_to_bottom", lambda: calls.append("bottom")
    )
    return calls


async def settle() -> None:
    """Let call_soon callbacks run."""
    import asyncio

    await asyncio.sleep(0)


def test_reload_shows_the_log_and_scrolls_to_the_newest_line(
    proto: ui.Prototype,
    app: toga.App,
    log: logfile.LogRedirector,
    scrolls: list[str],
) -> None:
    """The text first, then the scroll once it has been laid out."""
    proto.reload_logs(proto.tabs)
    assert proto.log_text.value == "first\nsecond\nnewest\n"
    assert scrolls == []  # not yet: the scroll waits for layout
    run(app, settle())
    assert scrolls == ["bottom"]


def test_selecting_the_logs_tab_reloads_and_scrolls(
    proto: ui.Prototype,
    app: toga.App,
    log: logfile.LogRedirector,
    scrolls: list[str],
) -> None:
    """The tab change calls the same reload."""
    log.write("added since\n")
    log.flush()
    proto.tabs.current_tab = "Logs"  # selecting the tab fires tab_changed
    run(app, settle())
    assert "added since" in proto.log_text.value
    assert scrolls and set(scrolls) == {"bottom"}


def test_reload_without_a_log_changes_nothing(
    proto: ui.Prototype,
    app: toga.App,
    scrolls: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Development runs have no log file: no error, no scrolling."""
    monkeypatch.setattr(logfile, "_current", None)
    proto.log_text.value = "unchanged"
    proto.reload_logs(proto.tabs)
    run(app, settle())
    assert proto.log_text.value == "unchanged" and scrolls == []


def test_the_jump_button_scrolls_to_the_bottom_at_once(
    proto: ui.Prototype, scrolls: list[str]
) -> None:
    """It needs no reload and no knowledge of where the view is."""
    proto.jump_to_log_bottom(proto.tabs)
    assert scrolls == ["bottom"]


def test_the_logs_tab_has_reload_and_a_jump_button(proto: ui.Prototype) -> None:
    """Both are on the Logs tab."""
    logs = next(item for item in proto.tabs.content if item.text == "Logs")
    found: list[toga.Button] = []

    def walk(widget: toga.Widget) -> None:
        if isinstance(widget, toga.Button):
            found.append(widget)
        for child in widget.children:
            walk(child)

    walk(logs.content)
    assert [b.text for b in found] == [ui.LOG_RELOAD, ui.LOG_BOTTOM, ui.LOG_CLEAR]
    # Monochrome symbols, sized like the Setup toolbars', not words or emoji
    assert all(b.style.font_size == ui.SYMBOL_SIZE for b in found)
