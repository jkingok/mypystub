"""The launcher's tabs are laid out again when UIKit sizes them (iPadOS 26)."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from mypystub.ui_helpers import _tab_resized, follow_tab_sizes
from tests import support_ui  # noqa: F401 (selects the dummy backend)


class Content:
    """A tab's root widget impl, counting the refreshes asked of it."""

    def __init__(self) -> None:
        self.refreshes = 0
        self.interface = self

    def refresh(self) -> None:
        self.refreshes += 1


def container(width: float, height: float) -> Any:
    return SimpleNamespace(width=width, height=height, content=Content())


def test_a_new_size_refreshes_the_tab() -> None:
    resized = _tab_resized(None)
    tab = container(820, 1030)
    resized(tab)
    assert tab.content.refreshes == 1


def test_the_same_size_again_does_nothing() -> None:
    """UIKit lays the view out often; only a change of size is worth a layout."""
    resized = _tab_resized(None)
    tab = container(820, 1030)
    resized(tab)
    resized(tab)
    assert tab.content.refreshes == 1
    tab.width, tab.height = 1180, 670  # rotated
    resized(tab)
    assert tab.content.refreshes == 2


def test_on_shown_is_called_when_the_tab_first_has_a_size() -> None:
    """A tab selected at 0 by 0 is shown once it has a size, and only then."""
    shown: list[bool] = []
    resized = _tab_resized(lambda: shown.append(True))
    tab = container(0, 0)
    resized(tab)
    assert shown == []
    tab.width, tab.height = 820, 1030
    resized(tab)
    assert shown == [True]
    tab.width, tab.height = 1180, 670  # a rotation isn't a first showing
    resized(tab)
    assert shown == [True]


def test_a_tab_without_content_is_left_alone() -> None:
    resized = _tab_resized(lambda: pytest.fail("not shown"))
    resized(SimpleNamespace(width=820, height=1030, content=None))


def tabs_with(*containers: Any) -> Any:
    return SimpleNamespace(_impl=SimpleNamespace(sub_containers=list(containers)))


def test_every_tab_follows_its_size_on_ios(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "ios")
    first, second = container(0, 0), container(0, 0)
    follow_tab_sizes(tabs_with(first, second))
    assert callable(first.on_native_layout) and callable(second.on_native_layout)
    assert first.on_native_layout is not second.on_native_layout  # own sizes


def test_other_platforms_are_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "android")
    tab = container(0, 0)
    follow_tab_sizes(tabs_with(tab))
    assert not hasattr(tab, "on_native_layout")
