"""SafeArea stops UIKit adding the safe area to scrolling views a second time."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest
import toga

from mypystub.safe_area import Insets, SafeArea, SafeColumn
from tests import support_ui  # noqa: F401 (selects the dummy backend)

NEVER = 2  # UIScrollViewContentInsetAdjustmentNever
AUTOMATIC = 0


def view(native: Any) -> Any:
    return SimpleNamespace(_impl=SimpleNamespace(native=native))


def test_scrolling_views_are_not_adjusted_by_uikit() -> None:
    scroll = SimpleNamespace(contentInsetAdjustmentBehavior=AUTOMATIC)
    SafeArea._native_no_adjustment([view(scroll)])
    assert scroll.contentInsetAdjustmentBehavior == NEVER


def test_a_web_view_is_set_on_its_scroll_view() -> None:
    inner = SimpleNamespace(contentInsetAdjustmentBehavior=AUTOMATIC)
    SafeArea._native_no_adjustment([view(SimpleNamespace(scrollView=inner))])
    assert inner.contentInsetAdjustmentBehavior == NEVER


def test_new_insets_turn_it_off_on_ios(monkeypatch: pytest.MonkeyPatch) -> None:
    """Applying insets covers the box's scrolling widgets, once they change."""
    seen: list[list[toga.Widget]] = []
    monkeypatch.setattr(SafeArea, "_native_no_adjustment", staticmethod(seen.append))
    text = toga.MultilineTextInput(flex=1)
    box = SafeColumn(children=[toga.Label("Title"), text])
    monkeypatch.setattr(sys, "platform", "ios")
    box.set_insets(Insets(64, 0, 0, 0))
    box.set_insets(Insets(64, 0, 0, 0))  # unchanged: nothing more to do
    monkeypatch.undo()
    assert seen == [[text]]
