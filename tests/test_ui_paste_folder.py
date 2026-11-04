"""What the Paste button says when the pasteboard can't be read.

Skipped where toga_dummy isn't installed, such as on device.
"""

import os
from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import bridge, paste_import, ui
from tests.support_ui import run


def test_paste_reports_a_copied_folder(
    proto: ui.Prototype, app: toga.App, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A folder can't be read, and the error says what to do instead."""

    async def read_pasteboard(into: Path) -> None:
        raise ValueError(paste_import.FOLDER_MESSAGE)

    errors: list[str] = []

    async def error(message: str, title: str = "") -> None:
        errors.append(message)

    monkeypatch.setattr(bridge, "read_pasteboard", read_pasteboard)
    monkeypatch.setattr(proto, "error", error)
    proto.category = "Documents"
    run(app, proto.handle_paste())
    assert errors == [f"Couldn't paste: {paste_import.FOLDER_MESSAGE}"]
