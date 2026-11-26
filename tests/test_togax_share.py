"""togax_jkingok.share: the share sheet, and the desktops' fallbacks (#323)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from mypystub import share_items
from tests.support_android_share import Java
from togax_jkingok import _android_share, share


@pytest.fixture
def report(tmp_path: Path) -> Path:
    path = tmp_path / "about.txt"
    path.write_text("details")
    return path


@pytest.mark.parametrize(
    ("platform", "offered"),
    [
        ("ios", True),
        ("android", True),
        ("darwin", True),
        ("win32", True),
        ("linux", True),
        ("emscripten", False),
    ],
)
def test_where_sharing_does_something(
    monkeypatch: pytest.MonkeyPatch, platform: str, offered: bool
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    assert share.available() is offered
    assert share_items.share_available() is offered


def test_a_missing_file_says_so(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        share.share_file(tmp_path / "gone.txt")


def runs(monkeypatch: pytest.MonkeyPatch, status: int = 0) -> list[list[str]]:
    calls: list[list[str]] = []

    def run(args: list[str], check: bool) -> subprocess.CompletedProcess[bytes]:
        calls.append(args)
        return subprocess.CompletedProcess(args, status)

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_finder_selects_the_file(monkeypatch: pytest.MonkeyPatch, report: Path) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    calls = runs(monkeypatch)
    assert share.reveal(report) is True
    assert calls == [["open", "-R", str(report)]]
    assert share.reveal(report) is True
    runs(monkeypatch, status=1)
    assert share.reveal(report) is False


def test_explorer_selects_the_file(
    monkeypatch: pytest.MonkeyPatch, report: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    calls = runs(monkeypatch, status=1)  # Explorer's status means nothing
    assert share.reveal(report) is True
    assert calls == [["explorer", f"/select,{report}"]]


def test_linux_opens_the_folder(monkeypatch: pytest.MonkeyPatch, report: Path) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    opened: list[str] = []
    monkeypatch.setattr(
        share.webbrowser, "open", lambda url: opened.append(url) or True
    )
    assert share.share_file(report) is True
    assert opened == [report.parent.as_uri()]


def test_nowhere_to_share_on_the_web(
    monkeypatch: pytest.MonkeyPatch, report: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "emscripten")
    assert share.share_file(report) is False


def test_macos_falls_back_to_finder_without_cocoa(
    monkeypatch: pytest.MonkeyPatch, report: Path
) -> None:
    """No toga-cocoa (or no window): Finder still shows the file."""
    from togax_jkingok import _cocoa_share

    def no_cocoa(path: Path, window: Any) -> bool:
        raise ImportError("toga_cocoa")

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(_cocoa_share, "share", no_cocoa)
    calls = runs(monkeypatch)
    assert share.share_file(report) is True
    assert calls == [["open", "-R", str(report)]]


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("tip.py", "text/x-python"),
        ("app.pyz", "application/zip"),
        ("backup.zip", "application/zip"),
        ("about.txt", "text/plain"),
        ("app_runtime.log", "text/plain"),
        ("data.unknownext", "application/octet-stream"),
    ],
)
def test_mime_types(name: str, kind: str) -> None:
    assert _android_share.mime_type(Path(name)) == kind


def test_android_shares_by_content_uri(tmp_path: Path, report: Path) -> None:
    java = Java(tmp_path, tmp_path)
    uri = "content://example/about.txt"
    assert _android_share.share(report, "Share", lambda p: uri, 100, java.jclass)
    (chooser,) = java.started
    send = chooser.target
    assert chooser.action == "CHOOSER" and chooser.flags == 1
    assert chooser.title == "Share"
    assert send.action == "SEND" and send.type == "text/plain"
    assert send.extras == {"STREAM": uri, "SUBJECT": "about.txt"}
    assert send.clip == ("about.txt", uri) and send.flags == 1


def test_android_without_a_provider_sends_small_text(
    tmp_path: Path, report: Path
) -> None:
    java = Java(tmp_path, tmp_path)
    assert _android_share.share(report, "Share", None, 100, java.jclass)
    send = java.started[0].target
    assert send.type == "text/plain"
    assert send.extras == {"TEXT": "details", "SUBJECT": "about.txt"}


def test_android_without_a_provider_cant_send_the_rest(tmp_path: Path) -> None:
    java = Java(tmp_path, tmp_path)
    big = tmp_path / "big.txt"
    big.write_text("x" * 101)
    archive = tmp_path / "app.zip"
    archive.write_bytes(b"PK")
    assert not _android_share.share(big, "Share", None, 100, java.jclass)
    assert not _android_share.share(archive, "Share", None, 100, java.jclass)
    assert java.started == []


def test_the_log_is_shared_as_a_fresh_text_copy(tmp_path: Path) -> None:
    log = tmp_path / "app_runtime.log"
    log.write_text("line one\n")
    cache = tmp_path / "cache"
    name = "MyPyStub log {stamp}.txt"
    first = share_items.log_copy(log, cache, name)
    assert first.parent == cache / share_items.SHARE_FOLDER
    assert first.name.startswith("MyPyStub log ") and first.suffix == ".txt"
    assert first.read_text() == "line one\n"
    first.rename(first.with_name("MyPyStub log old.txt"))
    log.write_text("line two\n")
    second = share_items.log_copy(log, cache, name)
    assert [p.name for p in second.parent.iterdir()] == [second.name]
    assert second.read_text() == "line two\n"
