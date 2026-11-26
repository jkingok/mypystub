"""SafeArea on a small phone in landscape with the keyboard up (#305)."""

from __future__ import annotations

import sys

import pytest
import toga

from tests import support_ui  # noqa: F401 (selects the dummy backend)
from togax_jkingok import OrientationBox
from togax_jkingok.safe_area import (
    NO_INSETS,
    Insets,
    insets_for,
    visible_height,
    widest,
    window_share,
)

# iPhone 13 mini in landscape: a tab's box under the 104-point title, the
# window 812 by 375 points, the keyboard leaving 40 points of the box clear
MINI = (0.0, 104.0, 812.0, 271.0, 812.0, 375.0)


def test_padding_comes_from_the_part_of_the_box_on_screen() -> None:
    """Toga makes a box taller than its space when its content can't fit.

    Padding from that taller height made it taller again, 15 points a pass,
    without end; the visible height doesn't move, so neither does the padding.
    """
    paddings = []
    height = 271.0
    for _ in range(5):
        frame = (*MINI[:3], height, *MINI[4:])
        bottom = insets_for(NO_INSETS, visible_height(height, frame), 40).bottom
        paddings.append(bottom)
        height = bottom + 55  # the content's minimum: the box grows to fit it
    assert paddings == [231] * 5


def test_a_box_inside_the_window_keeps_its_height() -> None:
    assert visible_height(271, MINI) == 271
    assert visible_height(500, ()) == 500  # no frame: as before


def test_the_window_says_where_the_notch_is() -> None:
    """A view reporting no side insets still clears the notch (#305)."""
    landscape = Insets(0, 50, 21, 50)
    assert window_share(landscape, MINI) == Insets(0, 50, 21, 50)


def test_only_the_window_insets_that_reach_the_view_count() -> None:
    # A box under the title bar is clear of the status bar's 50 points
    portrait = Insets(50, 0, 34, 0)
    box = (0.0, 104.0, 375.0, 600.0, 375.0, 812.0)
    assert window_share(portrait, box) == Insets(0, 0, 0, 0)
    # A box reaching the bottom gets the home indicator
    box = (0.0, 104.0, 375.0, 708.0, 375.0, 812.0)
    assert window_share(portrait, box) == Insets(0, 0, 34, 0)


def test_without_a_frame_the_window_adds_nothing() -> None:
    assert window_share(Insets(0, 50, 21, 50), ()) == NO_INSETS


def test_the_larger_of_view_and_window_wins_on_each_edge() -> None:
    assert widest(Insets(0, 0, 21, 0), Insets(0, 50, 0, 50)) == Insets(0, 50, 21, 50)


def test_a_question_keeps_its_own_size_beside_its_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(toga.App, "app", None)  # direction changes at once
    label = toga.Label("Who are you?")
    field = toga.TextInput(flex=1)
    box = OrientationBox(label, field, equal=False)
    assert label.style.flex == 0 and field.style.flex == 1
    box.update_orientation(812, 271)  # landscape
    assert not box.portrait
    box.update_orientation(375, 600)
    assert box.portrait


def test_equal_shares_are_still_the_default() -> None:
    first, second = toga.Box(), toga.Box()
    OrientationBox(first, second)
    assert first.style.flex == second.style.flex == 1


# The scene's reference window (iOS 18.5 and 27.2 keep Toga's window's
# portrait insets in landscape)


def test_reference_insets_are_iOS_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from togax_jkingok import _ios_reference

    monkeypatch.setattr(sys, "platform", "android")
    assert _ios_reference.scene_insets(object()) is None


def test_one_reference_window_per_scene(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from togax_jkingok import _ios_reference

    made: list[object] = []

    def make(scene: object) -> object:
        made.append(scene)
        return SimpleNamespace(
            safeAreaInsets=SimpleNamespace(top=0, right=50, bottom=20, left=50)
        )

    monkeypatch.setattr(sys, "platform", "ios")
    monkeypatch.setattr(_ios_reference, "_windows", {})
    monkeypatch.setattr(_ios_reference, "_make", make)
    scene = SimpleNamespace(ptr=SimpleNamespace(value=1234))
    window = SimpleNamespace(windowScene=scene)
    assert _ios_reference.scene_insets(window) == (0, 50, 20, 50)
    assert _ios_reference.scene_insets(window) == (0, 50, 20, 50)
    assert made == [scene]


def test_a_rotation_is_read_again_once(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from togax_jkingok.safe_area import REREAD_DELAY, SafeColumn

    later: list[tuple[float, object]] = []
    loop = SimpleNamespace(call_later=lambda delay, f: later.append((delay, f)))
    monkeypatch.setattr(toga.App, "app", SimpleNamespace(loop=loop))
    box = SafeColumn()
    box._read_again_if_resized(MINI)
    box._read_again_if_resized(MINI)  # the same size: nothing more
    assert len(later) == 1 and later[0][0] == REREAD_DELAY
    box._read_again_if_resized((0.0, 104.0, 375.0, 625.0, 375.0, 812.0))
    assert len(later) == 2
