"""The Paste preview is the Info page of what is being added (#189).

Skipped where toga_dummy isn't installed, such as on device.
"""

import os
import zipfile
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import bridge, info_pages, ui, ui_paste
from tests.support_ui import run

SCRIPT = (
    '"""Tracks interest."""\n# /// script\n# dependencies = ["rich"]\n# ///\nprint(1)\n'
)


def test_pasted_text_previews_exactly_as_its_info_will_look(
    proto: ui.Prototype, tmp_path: Path
) -> None:
    """Title, description, dependencies and source: the same page, byte for byte."""
    proto._pending_suggestion = "interest tracker.py"
    title, body, can_import = proto.import_preview("text", SCRIPT)
    imported = tmp_path / "interest tracker.py"
    imported.write_text(SCRIPT)
    assert can_import and title == "Paste"
    assert body == info_pages.script_info_html(imported, "interest tracker")
    assert "Tracks interest." in body and "Dependencies" in body


def test_pasted_text_without_a_suggested_name_uses_the_timestamp_name(
    proto: ui.Prototype,
) -> None:
    """The page is headed with the name it would be offered."""
    proto._pending_suggestion = None
    _, body, _ = proto.import_preview("text", SCRIPT)
    assert "<h1>pasted_" in body and ".py," in body


def test_a_pasted_project_archive_previews_the_project(
    proto: ui.Prototype, tmp_path: Path
) -> None:
    """The archive shows what it holds, then its contents."""
    archive = tmp_path / "proj.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("proj/pyproject.toml", '[project]\nname="proj"\nversion="1"\n')
    name, body, can_import = proto.import_preview("file", str(archive))
    assert can_import and name == "proj.zip"
    assert "<h1>proj</h1>" in body and "Version: 1" in body
    assert "Archive contents" in body


def test_a_pasted_python_file_still_previews_as_info(
    proto: ui.Prototype, tmp_path: Path
) -> None:
    """Unchanged: a .py file is its Info page."""
    path = tmp_path / "tool.py"
    path.write_text(SCRIPT)
    _, body, can_import = proto.import_preview("file", str(path))
    assert can_import and body == info_pages.script_info_html(path, "tool")


def test_pasted_texts_name_is_fixed_when_paste_is_pressed(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The preview and the name prompt agree, even if the minute turns over."""
    times: Iterator[datetime] = iter(
        datetime(2026, 11, 8, 18, minute) for minute in range(3, 60)
    )

    class Clock(datetime):
        @classmethod
        def now(cls, tz: object = None) -> "Clock":  # type: ignore[override]
            return next(times)  # type: ignore[return-value]

    shown: list[str] = []
    asked: list[str] = []

    async def read_pasteboard(into: Path) -> tuple[str, str] | None:
        return ("text", SCRIPT)

    async def ask_text(title: str, label: str, initial: str) -> str | None:
        asked.append(initial)
        return initial

    async def info(text: str, title: str | None = None) -> None:
        pass

    monkeypatch.setattr(ui_paste, "datetime", Clock)
    monkeypatch.setattr(bridge, "read_pasteboard", read_pasteboard)
    monkeypatch.setattr(bridge, "suggested_name", lambda: None)
    monkeypatch.setattr(
        proto, "show_import_preview", lambda title, body, ok: shown.append(body)
    )
    monkeypatch.setattr(proto, "ask_text", ask_text)
    monkeypatch.setattr(proto, "info", info)
    run(app, proto.handle_paste())
    run(app, proto._do_import())
    assert "<h1>pasted_20261108_1803</h1>" in shown[0]
    assert asked == ["pasted_20261108_1803"]
    assert (docs / "pasted_20261108_1803.py").is_file()
