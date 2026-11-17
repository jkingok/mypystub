"""The AndroidX Back callback (android_back), with stand-ins for Chaquopy."""

import importlib
import sys
import types
from pathlib import Path
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


class PyBackCallback:
    """au.id.jking.mypystub.PyBackCallback: the Java subclass, with a Handler."""

    Handler = object

    def __init__(self, handler: Any) -> None:
        self.handler = handler
        self.enabled = True

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def handleOnBackPressed(self) -> None:
        self.handler.handle()


@pytest.fixture
def android_back(monkeypatch: pytest.MonkeyPatch) -> Any:
    dispatcher = Dispatcher()
    activity = types.SimpleNamespace(getOnBackPressedDispatcher=lambda: dispatcher)
    java = types.ModuleType("java")
    java.dynamic_proxy = lambda interface: object  # type: ignore[attr-defined]

    def jclass(name: str) -> Any:
        if name == "au.id.jking.mypystub.PyBackCallback":
            return PyBackCallback
        return types.SimpleNamespace(singletonThis=activity)

    java.jclass = jclass  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "java", java)
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


def test_the_java_subclass_has_a_constructor_python_can_call() -> None:
    """A static proxy of OnBackPressedCallback can't compile (#277's cause)."""
    root = Path(__file__).resolve().parent.parent
    java = (
        root / "assets/android/java/au/id/jking/mypystub/PyBackCallback.java"
    ).read_text()
    assert "extends OnBackPressedCallback" in java
    assert "super(true)" in java
    pyproject = (root / "pyproject.toml").read_text()
    assert '"mypystub.android_back"' not in pyproject  # no static proxy for it
