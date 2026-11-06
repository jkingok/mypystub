"""Pasted text is offered the name the copying app gave it (as .py).

Skipped where toga_dummy isn't installed, such as on device.
"""

import os
from datetime import datetime
from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import bridge, paste_import, ui
from tests.support_ui import run

NOW = datetime(2026, 11, 5, 9, 5)


@pytest.mark.parametrize(
    ("suggested", "expected"),
    [
        ("interest tracker.py", "interest tracker"),
        ("tracker.txt", "tracker"),  # never anything but .py once saved
        ("sub/dir/tool.PY", "tool"),
        ("", "pasted_20261105_0905"),
        (None, "pasted_20261105_0905"),
        ("..", "pasted_20261105_0905"),
    ],
)
def test_suggested_stem(suggested: str | None, expected: str) -> None:
    """The offer is the copied name without .py, or the time when there's none."""
    assert paste_import.suggested_stem(suggested, NOW) == expected


def test_paste_offers_the_copied_items_name(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The name prompt starts from the item's own name, and the file is .py."""
    asked: list[str] = []

    async def read_pasteboard(into: Path) -> tuple[str, str] | None:
        return ("text", "print('hi')\n")

    async def ask_text(title: str, label: str, initial: str) -> str | None:
        asked.append(initial)
        return initial

    async def info(text: str, title: str | None = None) -> None:
        pass

    monkeypatch.setattr(bridge, "read_pasteboard", read_pasteboard)
    monkeypatch.setattr(bridge, "suggested_name", lambda: "interest tracker.py")
    monkeypatch.setattr(proto, "ask_text", ask_text)
    monkeypatch.setattr(proto, "info", info)
    run(app, proto.handle_paste())
    run(app, proto._do_import())
    assert asked == ["interest tracker"]
    assert (docs / "interest tracker.py").read_text() == "print('hi')\n"
