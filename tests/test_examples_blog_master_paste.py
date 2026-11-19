"""blog_master pastes an image from Android's clipboard (#264).

Chaquopy's ``java`` module is replaced by stand-ins, so the clipboard logic is
checked on desktop. The real thing needs a device or emulator.
"""

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest

FUNCTIONS = (
    Path(__file__).parent.parent
    / "src/mypystub/resources/examples/contrib/jkingok/blog_master/src/blog_master"
    / "functions.py"
)
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 600  # more than one read's worth


class Stream:
    """An InputStream over `data`, read into a jarray-like buffer."""

    def __init__(self, data: bytes) -> None:
        self.data, self.closed = data, False

    def read(self, buffer: bytearray) -> int:
        if not self.data:
            return -1
        count = min(len(buffer), len(self.data))
        buffer[:count] = self.data[:count]
        self.data = self.data[count:]
        return count

    def close(self) -> None:
        self.closed = True


def fake_java(items: list[tuple[str | None, str, bytes]]) -> types.ModuleType:
    """A ``java`` module whose clipboard holds `items` (uri, type, bytes)."""
    streams: dict[str, Stream] = {}

    class Item:
        def __init__(self, uri: str | None) -> None:
            self.uri = uri

        def getUri(self) -> str | None:
            return self.uri

    class Clip:
        def getItemCount(self) -> int:
            return len(items)

        def getItemAt(self, index: int) -> Item:
            return Item(items[index][0])

        def getDescription(self) -> Any:
            return None

    class Resolver:
        def getType(self, uri: str) -> str:
            return next(kind for u, kind, _ in items if u == uri)

        def openInputStream(self, uri: str) -> Stream:
            data = next(data for u, _, data in items if u == uri)
            streams[uri] = Stream(data)
            return streams[uri]

    class Clipboard:
        def getPrimaryClip(self) -> Clip | None:
            return Clip() if items else None

    class Activity:
        def getSystemService(self, name: str) -> Clipboard:
            return Clipboard()

        def getContentResolver(self) -> Resolver:
            return Resolver()

    classes = {
        "org.beeware.android.MainActivity": types.SimpleNamespace(
            singletonThis=Activity()
        ),
        "android.content.Context": types.SimpleNamespace(CLIPBOARD_SERVICE="clip"),
    }
    module = types.ModuleType("java")
    module.jclass = classes.__getitem__  # type: ignore[attr-defined]
    module.jbyte = object()  # type: ignore[attr-defined]
    module.jarray = lambda kind: bytearray  # type: ignore[attr-defined]
    module.streams = streams  # type: ignore[attr-defined]
    return module


def load(monkeypatch: pytest.MonkeyPatch, java: types.ModuleType) -> Any:
    monkeypatch.setitem(sys.modules, "java", java)
    spec = importlib.util.spec_from_file_location("blog_master_functions", FUNCTIONS)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_an_image_is_saved_as_it_is(tmp_path: Path, monkeypatch) -> None:
    java = fake_java([("content://x/1", "image/png", PNG)])
    functions = load(monkeypatch, java)
    target = tmp_path / "logo.png"
    assert functions.android_image_to_file(str(target)) is True
    assert target.read_bytes() == PNG
    assert java.streams["content://x/1"].closed  # type: ignore[attr-defined]


def test_the_first_image_wins_over_other_items(tmp_path: Path, monkeypatch) -> None:
    java = fake_java(
        [
            (None, "", b""),  # a text item has no URI
            ("content://x/doc", "application/pdf", b"%PDF"),
            ("content://x/pic", "image/jpeg", b"\xff\xd8jpeg"),
        ]
    )
    target = tmp_path / "logo.png"
    assert load(monkeypatch, java).android_image_to_file(str(target)) is True
    assert target.read_bytes() == b"\xff\xd8jpeg"


@pytest.mark.parametrize(
    "items", [[], [(None, "", b"")], [("content://x/doc", "text/plain", b"hi")]]
)
def test_no_image_is_reported(tmp_path: Path, monkeypatch, items: list, capsys) -> None:
    target = tmp_path / "logo.png"
    assert (
        load(monkeypatch, fake_java(items)).android_image_to_file(str(target)) is False
    )
    assert not target.exists()
    assert capsys.readouterr().out.strip()  # it says why


def test_android_goes_to_the_android_clipboard(monkeypatch, tmp_path: Path) -> None:
    functions = load(monkeypatch, fake_java([("content://x/1", "image/png", PNG)]))
    monkeypatch.setattr(sys, "platform", "android")
    target = tmp_path / "logo.png"
    assert functions.save_image_from_pasteboard(str(target)) is True
