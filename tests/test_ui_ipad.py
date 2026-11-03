"""UI tests for the iPad's tab row.

Skipped where toga_dummy isn't installed, such as on device.
"""

import os
from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import ui
from tests.support_ui import (
    ICONS,
)

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
