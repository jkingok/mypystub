"""Android's Activity recreated in a live process: the UI is built again (#275)."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest
import toga

from mypystub import app as app_module


class Windows(set[Any]):
    """toga's WindowSet, as far as it is used."""

    def discard(self, window: Any) -> None:
        super().discard(window)


def fake_app(listener_native: object | None) -> Any:
    """A Toga app whose Android listener belongs to `listener_native`."""
    created: list[str] = []
    impl = types.SimpleNamespace(
        _listener=None
        if listener_native is None
        else types.SimpleNamespace(native=listener_native),
        create=lambda: created.append("create"),
    )
    return types.SimpleNamespace(
        _impl=impl,
        windows=Windows({"old window"}),
        commands=types.SimpleNamespace(on_change=lambda: None),
        loop=types.SimpleNamespace(call_soon=lambda fn: created.append("cascade")),
        created=created,
    )


@pytest.fixture
def android(monkeypatch: pytest.MonkeyPatch) -> object:
    """Pretend to be Android, whose current Activity is the returned object."""
    current = object()
    java = types.ModuleType("java")
    java.jclass = lambda name: types.SimpleNamespace(singletonThis=current)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "java", java)
    monkeypatch.setattr(app_module.sys, "platform", "android")
    return current


def test_a_new_activity_is_detected(android: object) -> None:
    assert app_module.activity_was_recreated(fake_app(object())) is True


def test_the_same_activity_is_not(android: object) -> None:
    assert app_module.activity_was_recreated(fake_app(android)) is False


def test_an_app_with_no_listener_yet_is_not(android: object) -> None:
    assert app_module.activity_was_recreated(fake_app(None)) is False


def test_it_is_never_true_off_android() -> None:
    assert app_module.activity_was_recreated(fake_app(object())) is False


def test_main_builds_the_ui_again_for_a_new_activity(
    android: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = fake_app(object())
    monkeypatch.setattr(toga.App, "app", existing, raising=False)
    assert app_module.main() is None
    assert existing.created == ["create"]  # not the cascade into the old window
    assert not existing.windows  # Android allows only one window
    assert existing.commands.on_change is None  # startup sets it again


def test_main_still_cascades_into_a_live_activity(
    android: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = fake_app(android)
    monkeypatch.setattr(toga.App, "app", existing, raising=False)
    assert app_module.main() is None
    assert existing.created == ["cascade"]
    assert existing.windows == {"old window"}
