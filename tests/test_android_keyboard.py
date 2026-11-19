"""Putting the keyboard away when a question is answered, with Chaquopy faked.

Android leaves its keyboard up when the focused field is taken off the screen
(it moves the focus to the tab bar), which left the Script tab laid out under
an open keyboard after input() was answered.
"""

from __future__ import annotations

import asyncio
import sys
import types
from typing import Any

import pytest

from mypystub import android_keyboard, ui_base
from tests.support_ui import wait_for


class Manager:
    """An InputMethodManager that records what it was asked to hide."""

    def __init__(self) -> None:
        self.hidden: list[Any] = []

    def hideSoftInputFromWindow(self, token: Any, flags: int) -> bool:
        self.hidden.append((token, flags))
        return True


class View:
    """An Android View with (or, once detached, without) a window token."""

    def __init__(self, token: Any = "field window") -> None:
        self.token = token
        self.focused = True

    def getWindowToken(self) -> Any:
        return self.token

    def clearFocus(self) -> None:
        self.focused = False


class Activity:
    """MainActivity, with its window's decor view and the focused view."""

    def __init__(self, manager: Manager, focused: View | None = None) -> None:
        self.manager = manager
        self.focused = focused
        self.decor = View("activity window")

    def getSystemService(self, name: str) -> Manager:
        assert name == "input_method"
        return self.manager

    def getWindow(self) -> Any:
        return types.SimpleNamespace(getDecorView=lambda: self.decor)

    def getCurrentFocus(self) -> View | None:
        return self.focused


def fake_java(monkeypatch: pytest.MonkeyPatch, activity: Activity) -> None:
    classes = {
        "android.content.Context": types.SimpleNamespace(
            INPUT_METHOD_SERVICE="input_method"
        ),
        "org.beeware.android.MainActivity": types.SimpleNamespace(
            singletonThis=activity
        ),
    }
    module = types.ModuleType("java")
    module.jclass = classes.__getitem__  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "java", module)


def test_hides_the_keyboard_and_drops_focus(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = Manager()
    fake_java(monkeypatch, Activity(manager))
    view = View()
    android_keyboard.hide(view)
    assert manager.hidden == [("field window", 0)]
    assert not view.focused


def test_a_detached_view_uses_the_activitys_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Off the screen it has no token; the focus the tab bar took goes too."""
    manager = Manager()
    tab_bar = View()
    fake_java(monkeypatch, Activity(manager, focused=tab_bar))
    android_keyboard.hide(View(token=None))
    assert manager.hidden == [("activity window", 0)]
    assert not tab_bar.focused


def test_the_keyboard_goes_when_no_question_follows(
    proto: Any, app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed: list[Any] = []
    monkeypatch.setattr(proto, "close_keyboard", lambda widget: closed.append(widget))
    proto.toggle_password(True)
    proto.toggle_password(False)
    wait_for(app, lambda: closed == [proto.password_text])


def test_the_keyboard_stays_for_the_next_question(
    proto: Any, app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A REPL asks again at once: its keyboard isn't closed between prompts."""
    closed: list[Any] = []
    monkeypatch.setattr(proto, "close_keyboard", lambda widget: closed.append(widget))
    proto.toggle_input(True)
    proto.toggle_input(False)
    proto.toggle_input(True)  # the next prompt, before the grace period ends
    app.loop.run_until_complete(asyncio.sleep(ui_base.KEYBOARD_GRACE * 2))
    assert closed == []
    proto.toggle_input(False)


def test_close_keyboard_uses_android_keyboard_on_android(
    proto: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    hidden: list[Any] = []
    monkeypatch.setattr(sys, "platform", "android")
    monkeypatch.setattr(android_keyboard, "hide", hidden.append)
    field = types.SimpleNamespace(_impl=types.SimpleNamespace(native="edit text"))
    proto.close_keyboard(field)
    assert hidden == ["edit text"]
