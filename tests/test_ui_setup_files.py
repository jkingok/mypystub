"""The Setup tab's "Open Documents in Files" button (#181).

Skipped where toga_dummy isn't installed, such as on device.
"""

import os
from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import files_app, ui
from tests.support_ui import run


def button_texts(widgets: list[toga.Widget]) -> list[str]:
    """The text of every button in `widgets`, however deeply nested."""
    found: list[str] = []

    def walk(widget: toga.Widget) -> None:
        if isinstance(widget, toga.Button):
            found.append(widget.text)
        for child in widget.children:
            walk(child)

    for widget in widgets:
        walk(widget)
    return found


def test_the_setup_menu_has_the_button(proto: ui.Prototype) -> None:
    """It is offered in the App section."""
    assert "Open Documents in Files" in button_texts(proto.setup_sections())


def test_the_button_opens_the_documents_folder(
    proto: ui.Prototype, app: toga.App, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The folder the launcher lists as Documents is the one opened."""
    opened: list[Path] = []
    monkeypatch.setattr(
        files_app, "open_in_files", lambda folder: opened.append(folder) or True
    )
    run(app, proto.handle_open_files(proto.update_all_button))
    assert opened == [proto.category_dirs()["Documents"]]


def test_a_failure_is_shown(
    proto: ui.Prototype, app: toga.App, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If it can't be opened, the user is told where it was meant to go."""
    shown: list[tuple[str, str | None]] = []

    async def info(text: str, title: str | None = None) -> None:
        shown.append((text, title))

    monkeypatch.setattr(files_app, "open_in_files", lambda folder: False)
    monkeypatch.setattr(proto, "info", info)
    run(app, proto.handle_open_files(proto.update_all_button))
    assert len(shown) == 1 and shown[0][1] == "Files"
    assert str(proto.category_dirs()["Documents"]) in shown[0][0]
