"""A right-click on a macOS list row shows the actions without selecting it.

The Objective-C subclass itself needs Cocoa, so it is checked on a Mac (see the
PR); these tests cover what decides the menu and how install() behaves.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from mypystub import cocoa_list


def impl(primary: bool, secondary: bool) -> Any:
    interface = SimpleNamespace(_primary_action="Info", _secondary_action="Setup")
    return SimpleNamespace(
        interface=interface,
        primary_action_enabled=primary,
        secondary_action_enabled=secondary,
    )


def test_the_menu_has_the_enabled_actions_in_order() -> None:
    assert cocoa_list.menu_titles(impl(True, True)) == [
        ("Info", "primaryActionOnRow:"),
        ("Setup", "secondaryActionOnRow:"),
    ]
    assert cocoa_list.menu_titles(impl(False, True)) == [
        ("Setup", "secondaryActionOnRow:")
    ]
    assert cocoa_list.menu_titles(impl(False, False)) == []


@pytest.fixture
def fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cocoa_list, "_installed", False)


def test_without_toga_cocoa_it_says_so_and_changes_nothing(
    fresh: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setitem(sys.modules, "toga_cocoa", None)  # import fails
    monkeypatch.setitem(sys.modules, "toga_cocoa.widgets", None)
    assert cocoa_list.install() is False
    assert "Right-click still selects the row" in caplog.text
    assert cocoa_list._installed is False


def test_installing_twice_is_harmless(
    fresh: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    made: list[Any] = []
    module = SimpleNamespace(
        TogaList=SimpleNamespace(instancesRespondToSelector=lambda selector: True),
        NSMenu=object(),
    )
    widgets = SimpleNamespace(detailedlist=module)
    monkeypatch.setitem(sys.modules, "toga_cocoa", SimpleNamespace(widgets=widgets))
    monkeypatch.setitem(sys.modules, "toga_cocoa.widgets", widgets)
    monkeypatch.setitem(sys.modules, "toga_cocoa.widgets.detailedlist", module)
    monkeypatch.setitem(
        sys.modules, "rubicon.objc", SimpleNamespace(SEL=lambda name: name)
    )
    monkeypatch.setattr(
        cocoa_list, "make_list_class", lambda m: made.append(m) or "Replacement"
    )
    assert cocoa_list.install() is True
    assert cocoa_list.install() is True
    assert made == [module] and module.TogaList == "Replacement"


def test_an_unexpected_toga_is_left_alone(
    fresh: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = SimpleNamespace(
        TogaList=SimpleNamespace(instancesRespondToSelector=lambda selector: False),
        NSMenu=object(),
    )
    widgets = SimpleNamespace(detailedlist=module)
    monkeypatch.setitem(sys.modules, "toga_cocoa", SimpleNamespace(widgets=widgets))
    monkeypatch.setitem(sys.modules, "toga_cocoa.widgets", widgets)
    monkeypatch.setitem(sys.modules, "toga_cocoa.widgets.detailedlist", module)
    monkeypatch.setitem(
        sys.modules, "rubicon.objc", SimpleNamespace(SEL=lambda name: name)
    )
    original = module.TogaList
    assert cocoa_list.install() is False
    assert module.TogaList is original
