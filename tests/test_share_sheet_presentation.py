"""How share sheets are presented: a form sheet, with a safe popover anchor.

Plain logic with stand-ins for the UIKit objects, so it runs without a device.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from mypystub.bridge import UIModalPresentationFormSheet, UIPopoverArrowDirectionDown
from mypystub.ui_helpers import configure_share_presentation, share_anchor_rect

SRC = Path(__file__).resolve().parent.parent / "src" / "mypystub"
SHARE_CODE = [
    SRC / "ui_helpers.py",
    SRC / "resources/examples/joshua/media_hub/src/media_hub/widgets.py",
]


class FakeActivityController:
    """Stands in for UIActivityViewController, whose popover getter is a method."""

    def __init__(self, popover: Any) -> None:
        self.modalPresentationStyle = 0
        self._popover = popover

    def popoverPresentationController(self) -> Any:
        return self._popover


def view(width: float, height: float) -> SimpleNamespace:
    """A stand-in UIView with bounds of the given size."""
    return SimpleNamespace(
        bounds=SimpleNamespace(size=SimpleNamespace(width=width, height=height))
    )


@pytest.mark.parametrize(("width", "height"), [(375, 667), (820, 1180), (0, 0)])
def test_anchor_is_a_point_inside_the_view(width: float, height: float) -> None:
    """The anchor has no size and sits at the bottom centre, never the whole view."""
    x, y, w, h = share_anchor_rect(width, height)
    assert (w, h) == (0, 0)
    assert x == width / 2
    assert 0 <= y <= height
    assert y >= height - 1


def test_form_sheet_with_no_popover() -> None:
    """On iPhone and iPad a form sheet has no popover, and nothing else is set."""
    vc = FakeActivityController(None)
    configure_share_presentation(vc, view(375, 667), lambda *r: r)
    assert vc.modalPresentationStyle == UIModalPresentationFormSheet


def test_popover_gets_a_source_view_and_a_small_rect() -> None:
    """If iOS does use a popover, it points down at the bottom centre."""
    popover = SimpleNamespace()
    presenting = view(820, 1180)
    configure_share_presentation(
        FakeActivityController(popover), presenting, lambda *r: r
    )
    assert popover.sourceView is presenting
    assert popover.sourceRect == share_anchor_rect(820, 1180)
    assert popover.permittedArrowDirections == UIPopoverArrowDirectionDown


@pytest.mark.parametrize("path", SHARE_CODE, ids=lambda p: p.name)
def test_popover_controller_is_always_called(path: Path) -> None:
    """Reading it uncalled sets attributes on a rubicon method, not on UIKit."""
    uncalled = re.compile(r"\.popoverPresentationController\b(?!\()")
    assert not uncalled.findall(path.read_text())


def test_media_hub_presents_a_form_sheet() -> None:
    """Media Hub keeps its own standalone copy of the fix."""
    code = SHARE_CODE[1].read_text()
    assert "modalPresentationStyle = UIModalPresentationFormSheet" in code
    assert "UIModalPresentationFormSheet = 2" in code
    assert "popoverPresentationController()" in code
