"""UI tests for the pushed-screen fallback of ``ask_fields``.

On iOS the prompt is a native alert; these cover the screen used elsewhere.
Skipped where toga_dummy isn't installed, such as on device.
"""

import asyncio
import os

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import prompts, ui
from tests.support_ui import run


def buttons(app: toga.App) -> dict[str, toga.Button]:
    """The buttons on the prompt screen that's showing, by label."""
    found: dict[str, toga.Button] = {}

    def walk(widget: toga.Widget) -> None:
        if isinstance(widget, toga.Button):
            found[widget.text] = widget
        for child in widget.children:
            walk(child)

    walk(app.main_window.content)
    return found


def test_screen_prompt_returns_the_texts(proto: ui.Prototype, app: toga.App) -> None:
    """Done pops the screen and returns every field's text."""
    tabs = app.main_window.content

    async def go() -> list[str] | None:
        task = asyncio.ensure_future(
            proto.ask_fields_screen(
                "Add variable", "", [prompts.Field("Name"), prompts.Field("Value", "v")]
            )
        )
        await asyncio.sleep(0.01)
        name, value = proto.ask_text_fields
        assert (name.placeholder, value.value) == ("Name", "v")
        name.value = "A"
        buttons(app)["Done"]._impl.simulate_press()
        return await task

    assert run(app, go()) == ["A", "v"]
    assert app.main_window.content is tabs


def test_screen_prompt_cancel_returns_none(proto: ui.Prototype, app: toga.App) -> None:
    """Cancel pops the screen and returns None."""
    tabs = app.main_window.content

    async def go() -> list[str] | None:
        task = asyncio.ensure_future(
            proto.ask_fields_screen("Edit", "", [prompts.Field("Argument", "x")])
        )
        await asyncio.sleep(0.01)
        buttons(app)["Cancel"]._impl.simulate_press()
        return await task

    assert run(app, go()) is None
    assert app.main_window.content is tabs
