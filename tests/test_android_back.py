"""The AndroidX Back callback (android_back), with stand-ins for Chaquopy."""

import importlib
import sys
import types
from typing import Any

import pytest


class Dispatcher:
    def __init__(self) -> None:
        self.callbacks: list[Any] = []
        self.defaults = 0

    def addCallback(self, owner: Any, callback: Any) -> None:
        self.callbacks.append(callback)

    def onBackPressed(self) -> None:
        # Android goes through enabled callbacks, then its default
        for callback in reversed(self.callbacks):
            if callback.enabled:
                callback.handleOnBackPressed()
                return
        self.defaults += 1


class Callback:
    """androidx.activity.OnBackPressedCallback, as far as it is used."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = enabled


@pytest.fixture
def android_back(monkeypatch: pytest.MonkeyPatch) -> Any:
    dispatcher = Dispatcher()
    activity = types.SimpleNamespace(getOnBackPressedDispatcher=lambda: dispatcher)
    java = types.ModuleType("java")
    java.static_proxy = lambda base: base  # type: ignore[attr-defined]
    java.constructor = lambda types_: lambda f: f  # type: ignore[attr-defined]
    java.Override = lambda ret, args: lambda f: f  # type: ignore[attr-defined]
    java.jboolean = bool  # type: ignore[attr-defined]
    java.jvoid = None  # type: ignore[attr-defined]
    java.jclass = lambda name: types.SimpleNamespace(singletonThis=activity)  # type: ignore[attr-defined]
    androidx = types.ModuleType("androidx")
    activity_module = types.ModuleType("androidx.activity")
    activity_module.OnBackPressedCallback = Callback  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "java", java)
    monkeypatch.setitem(sys.modules, "androidx", androidx)
    monkeypatch.setitem(sys.modules, "androidx.activity", activity_module)
    monkeypatch.delitem(sys.modules, "mypystub.android_back", raising=False)
    module = importlib.import_module("mypystub.android_back")
    module.dispatcher = dispatcher  # type: ignore[attr-defined]
    yield module
    sys.modules.pop("mypystub.android_back", None)


def test_back_reaches_the_handler(android_back: Any) -> None:
    calls: list[str] = []
    android_back.install(lambda: calls.append("back") or True)
    android_back.dispatcher.onBackPressed()
    assert calls == ["back"] and android_back.dispatcher.defaults == 0


def test_declined_back_falls_through_to_android(android_back: Any) -> None:
    android_back.install(lambda: False)
    android_back.dispatcher.onBackPressed()
    assert android_back.dispatcher.defaults == 1
    (callback,) = android_back.dispatcher.callbacks
    assert callback.enabled  # ready for the next press


def test_a_failing_handler_still_lets_back_work(android_back: Any) -> None:
    def broken() -> bool:
        raise RuntimeError("oops")

    android_back.install(broken)
    android_back.dispatcher.onBackPressed()
    assert android_back.dispatcher.defaults == 1


def test_installing_again_replaces_the_handler(android_back: Any) -> None:
    calls: list[str] = []
    android_back.install(lambda: calls.append("first") or True)
    android_back.install(lambda: calls.append("second") or True)
    android_back.dispatcher.onBackPressed()
    assert calls == ["second"] and len(android_back.dispatcher.callbacks) == 1


def test_the_static_proxy_is_declared_for_the_build() -> None:
    from pathlib import Path

    pyproject = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text()
    assert '"mypystub.android_back"' in pyproject
