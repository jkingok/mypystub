"""A long press on an Android list row shows the actions without selecting it."""

from __future__ import annotations

import sys
import types
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any, ClassVar

import pytest

from mypystub import android_list


@dataclass
class Action:
    """Toga's Action: a name, its handler and whether it is enabled."""

    name: str
    handler: Callable[..., None]
    enabled: bool


class Builder:
    """android.app.AlertDialog.Builder, recording what it was asked to show."""

    shown: ClassVar[list[tuple[list[str], Any]]] = []

    def __init__(self, activity: Any) -> None:
        self.activity = activity

    def setItems(self, names: list[str], listener: Any) -> Builder:
        self.names, self.listener = names, listener
        return self

    def show(self) -> None:
        Builder.shown.append((self.names, self.listener))


class Interface:
    """The toga.DetailedList: its actions and rows, counting on_select calls."""

    _primary_action = "Info"
    _secondary_action = "Setup"
    data: ClassVar[list[str]] = ["row 0", "row 1"]

    def __init__(self) -> None:
        self.selected = 0

    def on_select(self) -> None:
        self.selected += 1

    def on_primary_action(self, **kwargs: Any) -> None:
        pass

    def on_secondary_action(self, **kwargs: Any) -> None:
        pass


class Impl:
    """The Android backend object."""

    _primary_action_enabled = True
    _secondary_action_enabled = True
    _native_activity = "activity"

    def __init__(self, interface: Interface) -> None:
        self.interface = interface
        self.selection: int | None = None

    def _set_selection(self, index: int) -> None:
        self.selection = index


class ToganLongClick:
    """Toga's listener as it is today: selects the row, then shows the dialog."""

    def __init__(self, impl: Impl, row_number: int) -> None:
        self.impl, self.interface, self.row_number = impl, impl.interface, row_number

    def onLongClick(self, _view: Any) -> bool:
        self.impl._set_selection(self.row_number)
        self.impl.interface.on_select()
        return True


@pytest.fixture
def toga_module(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """A stand-in ``toga_android.widgets.detailedlist``."""
    module = types.ModuleType("toga_android.widgets.detailedlist")
    module.DetailedListOnLongClickListener = ToganLongClick  # type: ignore[attr-defined]
    module.DetailedListActionListener = lambda actions, row: (actions, row)  # type: ignore[attr-defined]
    module.Action = Action  # type: ignore[attr-defined]
    module.AlertDialog = types.SimpleNamespace(Builder=Builder)  # type: ignore[attr-defined]
    module.suppress_reference_error = nullcontext  # type: ignore[attr-defined]
    for name, value in {
        "toga_android": types.ModuleType("toga_android"),
        "toga_android.widgets": types.ModuleType("toga_android.widgets"),
        "toga_android.widgets.detailedlist": module,
    }.items():
        monkeypatch.setitem(sys.modules, name, value)
    monkeypatch.setattr(android_list, "_installed", False)
    Builder.shown.clear()
    return module


def test_a_long_press_shows_the_actions_without_selecting(
    toga_module: types.ModuleType,
) -> None:
    assert android_list.install() is True
    interface = Interface()
    listener = ToganLongClick(Impl(interface), 1)
    assert listener.onLongClick(None) is True
    assert interface.selected == 0  # the row was not selected, so nothing ran
    ((names, (_actions, row)),) = Builder.shown
    assert names == ["Info", "Setup"]
    assert row == "row 1"


def test_disabled_actions_are_left_out(toga_module: types.ModuleType) -> None:
    android_list.install()
    impl = Impl(Interface())
    impl._secondary_action_enabled = False
    ToganLongClick(impl, 0).onLongClick(None)
    assert Builder.shown[0][0] == ["Info"]


def test_no_actions_shows_no_dialog_but_still_does_not_select(
    toga_module: types.ModuleType,
) -> None:
    android_list.install()
    impl = Impl(Interface())
    impl._primary_action_enabled = impl._secondary_action_enabled = False
    ToganLongClick(impl, 0).onLongClick(None)
    assert Builder.shown == []
    assert impl.interface.selected == 0


def test_installing_twice_changes_nothing(toga_module: types.ModuleType) -> None:
    android_list.install()
    first = ToganLongClick.onLongClick
    assert android_list.install() is True
    assert ToganLongClick.onLongClick is first


def test_a_changed_toga_is_left_alone(
    toga_module: types.ModuleType, caplog: pytest.LogCaptureFixture
) -> None:
    del toga_module.DetailedListActionListener  # type: ignore[attr-defined]
    original = ToganLongClick.onLongClick
    assert android_list.install() is False
    assert ToganLongClick.onLongClick is original
    assert "still selects" in caplog.text


def test_without_toga_android_it_says_so(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(android_list, "_installed", False)
    monkeypatch.delitem(sys.modules, "toga_android", raising=False)
    assert android_list.install() is False
    assert "still selects" in caplog.text
