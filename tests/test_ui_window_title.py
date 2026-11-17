"""The window title: "Launcher", or the last script on the Script tab (#235).

Skipped where toga_dummy isn't installed, such as on device.
"""

import pytest

pytest.importorskip("toga_dummy")

import toga

from mypystub import ui


def show(proto: ui.Prototype, tab: str) -> None:
    proto.tabs.current_tab = tab
    proto.refresh_tab(proto.tabs)


def test_launcher_on_every_tab_but_script(proto: ui.Prototype, app: toga.App) -> None:
    for tab in ("List", "Logs", "Setup", "Help", "Script"):
        show(proto, tab)
        assert app.main_window.title == "Launcher", tab


def test_the_script_tab_shows_the_last_run(proto: ui.Prototype, app: toga.App) -> None:
    proto.run_title = "Countdown"
    show(proto, "Script")
    assert app.main_window.title == "Countdown"
    show(proto, "List")
    assert app.main_window.title == "Launcher"


def test_a_title_a_script_set_is_put_back(proto: ui.Prototype, app: toga.App) -> None:
    proto.run_title = "Countdown"
    show(proto, "Script")
    app.main_window.title = "Set by the script"
    proto.end_script(proto.run_id)
    expected = "Countdown" if proto.tabs.current_tab.text == "Script" else "Launcher"
    assert app.main_window.title == expected


def test_back_from_a_screen_retitles_for_the_tab(
    proto: ui.Prototype, app: toga.App
) -> None:
    proto.run_title = "Countdown"
    show(proto, "Script")
    proto.push_screen("Info", toga.Box())
    assert app.main_window.title == "Info"
    proto.pop_screen()
    assert app.main_window.title == "Countdown"


def test_not_while_a_takeover_shows(proto: ui.Prototype, app: toga.App) -> None:
    app.main_window.content = toga.Box()  # a prototype's own screen
    app.main_window.title = "Prototype"
    proto.apply_window_title()
    assert app.main_window.title == "Prototype"
    app.main_window.content = proto.tabs
