"""The clipboard's desktop fallbacks, with WinForms and GTK faked.

macOS's was checked against the real pasteboard (see the PR); these platforms'
libraries aren't on the test machine, so stand-ins record what's asked.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from typing import Any, ClassVar

import pytest

from togax_jkingok import clipboard


@pytest.fixture
def loop() -> Any:
    """A loop of its own, made before a test fakes the platform.

    asyncio picks its loop by sys.platform, and on a faked "win32" it would
    reach for Windows-only modules.
    """
    private = asyncio.new_event_loop()
    yield private
    private.close()


class WinClipboard:
    """System.Windows.Forms.Clipboard."""

    files: ClassVar[list[str]] = []
    text = ""

    @classmethod
    def ContainsFileDropList(cls) -> bool:
        return bool(cls.files)

    @classmethod
    def GetFileDropList(cls) -> list[str]:
        return cls.files

    @classmethod
    def ContainsText(cls) -> bool:
        return bool(cls.text)

    @classmethod
    def GetText(cls) -> str:
        return cls.text

    @classmethod
    def SetText(cls, text: str) -> None:
        cls.text = text


@pytest.fixture
def windows(monkeypatch: pytest.MonkeyPatch) -> type[WinClipboard]:
    monkeypatch.setattr(sys, "platform", "win32")
    forms = types.ModuleType("System.Windows.Forms")
    forms.Clipboard = WinClipboard  # type: ignore[attr-defined]
    for name in ("System", "System.Windows"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "System.Windows.Forms", forms)
    WinClipboard.files, WinClipboard.text = [], ""
    return WinClipboard


def test_windows_text_round_trip(loop: Any, windows: type[WinClipboard]) -> None:
    assert clipboard.write_text("hello") is True
    assert loop.run_until_complete(clipboard.read(Path("."))) == clipboard.Text("hello")


def test_windows_prefers_a_copied_file(loop: Any, windows: type[WinClipboard]) -> None:
    windows.files, windows.text = [r"C:\Users\me\notes.py"], "also text"
    content = loop.run_until_complete(clipboard.read(Path(".")))
    assert isinstance(content, clipboard.File)
    assert content.path.name.endswith("notes.py")


class Gtk3Board:
    """Gtk.Clipboard (GTK 3)."""

    def __init__(self) -> None:
        self.text: str | None = None
        self.uris: list[str] = []

    def wait_for_uris(self) -> list[str]:
        return self.uris

    def wait_for_text(self) -> str | None:
        return self.text

    def set_text(self, text: str, length: int) -> None:
        self.text = text

    def store(self) -> None:
        pass


@pytest.fixture
def gtk3(monkeypatch: pytest.MonkeyPatch) -> Gtk3Board:
    monkeypatch.setattr(sys, "platform", "linux")
    board = Gtk3Board()
    gtk = types.SimpleNamespace(
        get_major_version=lambda: 3,
        Clipboard=types.SimpleNamespace(get=lambda selection: board),
    )
    gdk = types.SimpleNamespace(SELECTION_CLIPBOARD="CLIPBOARD")
    repository = types.ModuleType("gi.repository")
    repository.Gtk, repository.Gdk = gtk, gdk  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gi", types.ModuleType("gi"))
    monkeypatch.setitem(sys.modules, "gi.repository", repository)
    return board


def test_gtk3_text_round_trip(loop: Any, gtk3: Gtk3Board) -> None:
    assert clipboard.write_text("from gtk") is True
    assert loop.run_until_complete(clipboard.read(Path("."))) == clipboard.Text(
        "from gtk"
    )


def test_gtk3_reads_a_copied_file(loop: Any, gtk3: Gtk3Board) -> None:
    gtk3.uris = ["file:///home/me/My%20Notes.py"]
    content = loop.run_until_complete(clipboard.read(Path(".")))
    assert content == clipboard.File(Path("/home/me/My Notes.py"))


def test_a_desktop_without_its_backend_has_no_clipboard(
    loop: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setitem(sys.modules, "gi", None)  # import fails
    monkeypatch.setitem(sys.modules, "gi.repository", None)
    assert loop.run_until_complete(clipboard.read(Path("."))) is None
    assert clipboard.write_text("x") is False


def test_the_web_has_no_clipboard(loop: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "emscripten")
    assert loop.run_until_complete(clipboard.read(Path("."))) is None
    assert clipboard.write_text("x") is False
