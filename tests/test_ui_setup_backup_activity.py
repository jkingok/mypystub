"""Backup shows its progress at the foot of the Setup tab (#303).

The button keeps its label and icon; a spinner row below the menu says
"Backing up…" while the zip is made, and goes away when it's done.
"""

import threading
from pathlib import Path
from typing import Any

import pytest
import toga

from mypystub import backups, ui, ui_setup
from tests.support_ui import run


def test_backup_shows_and_hides_the_activity_row(
    proto: ui.Prototype, app: toga.App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[Any, str]] = []
    row = proto.setup_tab_activity
    assert row.style.display == "none"

    def create(*args: Any, **kwargs: Any) -> Path:
        seen.append((row.style.display, row.text.text))
        assert threading.current_thread() is not threading.main_thread()
        return tmp_path / "backup.zip"

    monkeypatch.setattr(backups, "create", create)
    monkeypatch.setattr(ui_setup, "open_share_sheet", lambda *args: None)
    button = toga.Button("Backup")
    run(app, proto.handle_backup_press(button))
    assert seen == [("pack", "Backing up…")]
    assert row.style.display == "none"
    assert button.text == "Backup" and button.enabled


def test_the_row_is_at_the_foot_of_the_setup_tab(proto: ui.Prototype) -> None:
    tab = proto.setup_tab_activity.parent
    assert tab is not None and tab.children[-1] is proto.setup_tab_activity
