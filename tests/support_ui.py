"""Helpers shared by the UI tests, run on Toga's dummy backend (#53, #140).

Importing this module skips the importing test file where toga_dummy isn't
installed, such as on device, and selects the dummy backend before Toga is used.
"""

import asyncio
import os
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import ui


def fresh_stack(proto: ui.Prototype) -> None:
    """Empty the shared window's content stack before a test.

    The window is shared by the module, so pages or takeovers an earlier test
    left open would otherwise change the depths later tests wait for.
    """
    stack = proto.content_stack()
    list.clear(stack)
    stack.floor = 0


def titles(p: ui.Prototype) -> list[str]:
    """Row titles currently in the list."""
    return [row.title for row in p.script_list.data]


def tap(
    p: ui.Prototype, title: str, monkeypatch: pytest.MonkeyPatch, app: toga.App
) -> None:
    """Select the row titled `title` on this list only, and run the handler."""
    # The dummy backend's selection is per widget, so lists from other tests
    # can't pick it up; the handler clears it once read (see the fixture).
    p.script_list._impl._set_value("selection", titles(p).index(title))
    run(app, p.handle_row_selection(p.script_list))


def run(app: toga.App, coro: Coroutine[Any, Any, Any]) -> Any:
    """Run `coro` on the app's loop."""
    return app.loop.run_until_complete(coro)


def wait_for(
    app: toga.App, condition: Callable[[], bool], timeout: float = 5.0
) -> None:
    """Run the app loop until `condition()` holds."""

    async def poll() -> None:
        for _ in range(int(timeout / 0.01)):
            if condition():
                return
            await asyncio.sleep(0.01)
        raise AssertionError("timed out waiting for the run to end")

    run(app, poll())


def run_to_end(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    source: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Write `source` as a script, tap it, and wait until its run has ended."""
    (docs / "case.py").write_text(source)
    proto.reload_menu(proto.script_list)
    tap(proto, "case", monkeypatch, app)
    wait_for(app, lambda: proto.ended_run == proto.run_id)


def row(p: ui.Prototype, title: str) -> Any:
    """The list row titled `title`."""
    return next(r for r in p.script_list.data if r.title == title)


def press(app: toga.App, button: toga.Button) -> None:
    """Press a button and let any async handler finish."""
    button._impl.simulate_press()
    run(app, asyncio.sleep(0.01))


def select(form_list: toga.DetailedList, handler: Callable, index: int) -> None:
    """Tap row `index` of one of the form's lists."""
    form_list._impl._set_value("selection", index)
    handler(form_list)
