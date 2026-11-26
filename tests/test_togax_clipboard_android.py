"""The Android clipboard (togax_jkingok), with Chaquopy's ``java`` module faked."""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from mypystub import bridge
from togax_jkingok import _android_clipboard as android_clipboard
from togax_jkingok import clipboard


class Item:
    """A ClipData.Item."""

    def __init__(self, text: str | None) -> None:
        self.text = text

    def getText(self) -> str | None:
        return self.text


class Clip:
    """A ClipData."""

    def __init__(self, items: list[Item]) -> None:
        self.items = items

    def getItemCount(self) -> int:
        return len(self.items)

    def getItemAt(self, index: int) -> Item:
        return self.items[index]


class Manager:
    """A ClipboardManager."""

    def __init__(self, clip: Clip | None) -> None:
        self.clip = clip

    def setPrimaryClip(self, clip: Clip) -> None:
        self.clip = clip

    def hasPrimaryClip(self) -> bool:
        return self.clip is not None

    def getPrimaryClip(self) -> Clip | None:
        return self.clip


def run_private(coroutine: Any) -> Any:
    """Run `coroutine` on a loop of its own, leaving the current loop alone.

    asyncio.run() would leave none current, which later UI tests need.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


def fake_java(monkeypatch: pytest.MonkeyPatch, manager: Manager | None) -> None:
    """Install a ``java`` module whose activity hands out `manager`."""

    class Activity:
        def getSystemService(self, name: str) -> Manager | None:
            return manager

    classes: dict[str, Any] = {
        "org.beeware.android.MainActivity": types.SimpleNamespace(
            singletonThis=Activity()
        ),
        "android.content.Context": types.SimpleNamespace(CLIPBOARD_SERVICE="clip"),
        "android.content.ClipData": types.SimpleNamespace(
            newPlainText=lambda label, text: Clip([Item(text)])
        ),
    }
    module = types.ModuleType("java")
    module.jclass = classes.__getitem__  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "java", module)


def test_reads_the_first_items_text(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_java(monkeypatch, Manager(Clip([Item("print(1)\n"), Item("other")])))
    assert android_clipboard.read_text() == "print(1)\n"


@pytest.mark.parametrize(
    "manager",
    [None, Manager(None), Manager(Clip([])), Manager(Clip([Item(None)]))],
)
def test_nothing_readable_is_none(
    monkeypatch: pytest.MonkeyPatch, manager: Manager | None
) -> None:
    fake_java(monkeypatch, manager)
    assert android_clipboard.read_text() is None


def test_bridge_pastes_text_on_android(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    fake_java(monkeypatch, Manager(Clip([Item("x = 1")])))
    monkeypatch.setattr(sys, "platform", "android")
    assert run_private(bridge.read_pasteboard(tmp_path)) == ("text", "x = 1")


def test_text_written_can_be_read_back(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = Manager(None)
    fake_java(monkeypatch, manager)
    monkeypatch.setattr(sys, "platform", "android")
    assert clipboard.write_text("copied") is True
    assert run_private(clipboard.read(Path("."))) == clipboard.Text("copied")
