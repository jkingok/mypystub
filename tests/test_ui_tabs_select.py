"""Selecting a tab refreshes the tab selected, not the one left behind.

toga_iOS reports a selection before its tab bar has switched, so the
launcher reads the current tab on the next turn of the loop.
Skipped where toga_dummy isn't installed, such as on device.
"""

import asyncio
import os
from typing import Any

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import ui
from tests.support_ui import run


@pytest.fixture
def refreshed(proto: ui.Prototype, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record which tab's content was loaded."""
    loaded: list[str] = []
    monkeypatch.setattr(proto, "reload_menu", lambda *a, **k: loaded.append("List"))
    monkeypatch.setattr(proto, "reload_logs", lambda *a, **k: loaded.append("Logs"))
    monkeypatch.setattr(proto, "show_help_page", lambda *a, **k: loaded.append("Help"))
    return loaded


def select_like_ios(proto: ui.Prototype, monkeypatch: pytest.MonkeyPatch) -> None:
    """Report a selection before switching, as UITabBarController does."""
    impl: Any = proto.tabs._impl

    def select(index: int) -> None:
        impl.interface.on_select()
        impl._set_value("current_tab_index", index)

    monkeypatch.setattr(impl, "set_current_tab_index", select)


def settle(app: toga.App) -> None:
    """Let the loop run what was scheduled for its next turn."""
    run(app, asyncio.sleep(0))


@pytest.mark.parametrize(("start", "chosen"), [("List", "Logs"), ("Logs", "List")])
def test_ios_order_loads_the_tab_chosen(
    proto: ui.Prototype,
    app: toga.App,
    refreshed: list[str],
    monkeypatch: pytest.MonkeyPatch,
    start: str,
    chosen: str,
) -> None:
    """Picking Logs from List loads the logs, not the list again."""
    proto.tabs.current_tab = start
    settle(app)
    refreshed.clear()
    select_like_ios(proto, monkeypatch)
    proto.tabs.current_tab = chosen
    settle(app)
    assert refreshed == [chosen]


def test_help_is_loaded_when_its_tab_is_chosen(
    proto: ui.Prototype,
    app: toga.App,
    refreshed: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Help tab draws its page; Setup and Script have nothing to load."""
    proto.tabs.current_tab = "Setup"
    settle(app)
    assert refreshed == []
    select_like_ios(proto, monkeypatch)
    proto.tabs.current_tab = "Help"
    settle(app)
    assert refreshed == ["Help"]
