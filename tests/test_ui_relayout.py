"""Laying screens out again on resize and tab changes, and hidden halves.

Uses Toga's dummy backend with its window given a size, so Pack lays things out
as it would on a device.
"""

from typing import Any

import pytest

pytest.importorskip("toga_dummy")

import toga
import toga_dummy.window as dummy_window

from tests import support_ui
from togax_jkingok import OrientationBox, relayout, relayout_on_resize


@pytest.fixture
def window(app: toga.App, monkeypatch: pytest.MonkeyPatch) -> Any:
    """The app's window, with a content area of a size the test sets."""
    size = {"width": 800, "height": 400}
    monkeypatch.setattr(
        dummy_window.Container,
        "width",
        property(lambda s: size["width"]),
        raising=False,
    )
    monkeypatch.setattr(
        dummy_window.Container,
        "height",
        property(lambda s: size["height"]),
        raising=False,
    )
    window = app.main_window
    window.size_for_test = size  # type: ignore[attr-defined]
    return window


def lay_out(app: toga.App, root: toga.Widget) -> None:
    root.refresh()
    support_ui.run(app, __import__("asyncio").sleep(0.01))  # direction changes queue
    root.refresh()


@pytest.mark.parametrize(("width", "height"), [(800, 400), (400, 800)])
def test_a_hidden_half_gives_its_space_to_the_other(
    app: toga.App, window: Any, width: int, height: int
) -> None:
    """Landscape side by side, portrait stacked; a hidden side takes nothing."""
    window.size_for_test.update(width=width, height=height)
    first, second = toga.MultilineTextInput(), toga.MultilineTextInput()
    box = OrientationBox(first, second, flex=1)
    window.content = toga.Column(children=[box], flex=1)
    lay_out(app, window.content)
    assert (first.layout.content_width, first.layout.content_height) == (
        (width // 2, height) if width > height else (width, height // 2)
    )
    second.style.display = "none"
    lay_out(app, window.content)
    assert (first.layout.content_width, first.layout.content_height) == (width, height)
    second.style.display = "pack"
    first.style.display = "none"
    lay_out(app, window.content)
    assert (second.layout.content_width, second.layout.content_height) == (
        width,
        height,
    )


def test_relayout_reaches_scroll_view_contents(app: toga.App) -> None:
    inner = toga.Column(children=[toga.Label("x")])
    refreshed: list[toga.Widget] = []
    original = inner.refresh
    inner.refresh = lambda: (refreshed.append(inner), original())[1]  # type: ignore[method-assign]
    relayout(toga.Column(children=[toga.ScrollContainer(content=inner)]))
    relayout(None)
    assert inner in refreshed


def test_a_resize_lays_out_again_once_per_size_and_keeps_the_old_handler(
    app: toga.App, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = toga.Window(title="resize test")
    called: list[str] = []
    window.on_resize = lambda w, **kw: called.append("old")
    relayout_on_resize(window)
    relayout_on_resize(window)  # a second install changes nothing
    laid: list[Any] = []
    monkeypatch.setattr("togax_jkingok.layout.relayout", lambda w: laid.append(w))
    window.content = toga.Box()
    window.on_resize()
    window.on_resize()  # same size: the old handler still runs, no new layout
    window.size = (500, 300)
    window.on_resize()
    assert called and set(called) == {
        "old"
    }  # every resize, including the one size= sends
    assert len(laid) == 2
    window.close()
