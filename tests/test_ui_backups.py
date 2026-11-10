"""The backups section of a row's Setup, and Info staying read only (#182).

Restore and Delete are the rows' swipe actions; see
test_ui_setup_form_layout.py for the swipes themselves.

Skipped where toga_dummy isn't installed, such as on device.
"""

import os
from datetime import datetime
from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import info_pages, run_backups, versions
from tests.support_ui import run

NOW = datetime(2026, 11, 5, 14, 32, 7)


class Said:
    """Stand-ins for the confirmation and the message."""

    def __init__(self) -> None:
        self.answer = True
        self.asked: list[str] = []
        self.told: list[str] = []

    async def ask(self, title: str, text: str) -> bool:
        self.asked.append(text)
        return self.answer

    async def tell(self, title: str, text: str) -> None:
        self.told.append(text)


@pytest.fixture
def tool(tmp_path: Path) -> Path:
    path = tmp_path / "tool.py"
    path.write_text("v1")
    versions.back_up(path, NOW)
    path.write_text("v2")
    return path


def section(tool: Path, said: Said, app: toga.App) -> run_backups.BackupsSection:
    return run_backups.BackupsSection(
        tool, ask=said.ask, tell=said.tell, now=lambda: datetime(2026, 11, 6, 9, 0, 0)
    )


def test_hidden_until_switched_on_and_counts(tool: Path, app: toga.App) -> None:
    s = section(tool, Said(), app)
    assert s.switch.text == "Backup versions (1)"
    assert s.details.style.display == "none"
    s.switch.value = True
    s.toggle(s.switch)
    assert s.details.style.display == "pack"


def test_no_backups_disables_the_switch(tmp_path: Path, app: toga.App) -> None:
    (tmp_path / "x.py").write_text("a")
    s = section(tmp_path / "x.py", Said(), app)
    assert s.switch.enabled is False and s.switch.text == "Backup versions"


def test_restore_asks_then_restores(tool: Path, app: toga.App) -> None:
    said = Said()
    s = section(tool, said, app)
    changed: list[bool] = []
    s.on_change = lambda: changed.append(True)
    run(app, s.restore(s.found[0]))
    assert tool.read_text() == "v1" and said.asked and changed
    assert len(versions.list_backups(tool)) == 2


def test_declining_changes_nothing(tool: Path, app: toga.App) -> None:
    said = Said()
    said.answer = False
    s = section(tool, said, app)
    run(app, s.restore(s.found[0]))
    run(app, s.delete(s.found[0]))
    assert tool.read_text() == "v2" and len(versions.list_backups(tool)) == 1


def test_delete_removes_the_backup_and_refreshes(tool: Path, app: toga.App) -> None:
    s = section(tool, Said(), app)
    run(app, s.delete(s.found[0]))
    assert versions.list_backups(tool) == [] and len(s.list.data) == 0


def test_info_is_read_only_and_does_not_list_backups(tool: Path) -> None:
    page = info_pages.script_info_html(tool, "tool")
    assert "mypystub-version" not in page and "Restore" not in page
