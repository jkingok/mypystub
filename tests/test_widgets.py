"""Tests for the launcher's reusable widgets (mypystub.widgets), on Toga's dummy backend."""

import os

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub.widgets import OrientationBox


@pytest.fixture(autouse=True)
def no_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a running app, a new direction applies at once."""
    monkeypatch.setattr(toga.App, "app", None)


def pair() -> tuple[OrientationBox, toga.Widget, toga.Widget]:
    """An OrientationBox holding two plain boxes."""
    first, second = toga.Box(), toga.Box()
    return OrientationBox(first, second), first, second


def test_holds_two_widgets_flexed_equally() -> None:
    """Both children share the space equally."""
    box, first, second = pair()
    assert box.children == [first, second]
    assert first.style.flex == second.style.flex == 1


def test_portrait_stacks_top_to_bottom() -> None:
    """Width <= height (including square) puts the widgets one above the other."""
    box, _, _ = pair()
    box.update_orientation(300, 600)
    assert box.style.direction == "column" and box.portrait
    box.update_orientation(500, 500)
    assert box.style.direction == "column"


def test_landscape_puts_them_side_by_side() -> None:
    """Width > height puts the widgets left and right."""
    box, _, _ = pair()
    box.update_orientation(800, 400)
    assert box.style.direction == "row" and not box.portrait
    box.update_orientation(400, 800)
    assert box.style.direction == "column"


def test_unknown_size_is_ignored() -> None:
    """Before layout there's no size; keep the current direction."""
    box, _, _ = pair()
    box.update_orientation(800, 400)
    box.update_orientation(0, 0)
    assert box.style.direction == "row"


def test_layout_reports_the_boxes_own_size() -> None:
    """After each layout the box checks its own size, not the window's."""
    box, _, _ = pair()
    box.layout.content_width, box.layout.content_height = 900, 300
    box.applicator.set_bounds()
    assert box.style.direction == "row"


def test_direction_changes_wait_for_the_apps_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inside a layout, the change is queued rather than re-laid-out at once."""
    queued: list = []
    loop = type("Loop", (), {"call_soon": lambda self, f, *a: queued.append((f, a))})
    monkeypatch.setattr(toga.App, "app", type("App", (), {"loop": loop()})())
    box, _, _ = pair()
    box.update_orientation(900, 300)
    assert box.style.direction == "column" and len(queued) == 1
    callback, args = queued.pop()
    callback(*args)
    assert box.style.direction == "row"
