"""The Setup form's layout: sections that scroll and fold, buttons that stay put.

On an iPhone SE, turning on Backup versions pushed the buttons off the screen,
and the form couldn't scroll. Now the sections scroll above a fixed row of
buttons, each section folds under its own switch, and backups are restored or
deleted by swiping their row.

Skipped where toga_dummy isn't installed, such as on device.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import run_backups, run_with, ui, versions
from tests.support_ui import row, run

NOW = datetime(2026, 11, 5, 14, 32, 7)


def flip(form: Any, name: str, value: bool) -> toga.Box:
    """Turn a section's switch on or off, as the user would; its body."""
    switch, body = form.sections[name]
    switch.value = value
    form._toggle_section(switch)
    return body


def walk(widget: toga.Widget) -> list[toga.Widget]:
    """`widget` and everything inside it, ScrollContainers included."""
    found = [widget]
    inner = list(widget.children) if widget.children else []
    if isinstance(widget, toga.ScrollContainer) and widget.content is not None:
        inner.append(widget.content)
    for child in inner:
        found += walk(child)
    return found


def test_sections_scroll_above_a_fixed_row_of_buttons(
    proto: ui.Prototype, config: Path
) -> None:
    form = proto.open_run_with(row(proto, "top"))
    assert form.content.children == [form.scroll, form.button_row]
    assert form.scroll.style.flex == 1 and form.scroll.horizontal is False
    buttons = [w for w in form.button_row.children if isinstance(w, toga.Button)]
    assert [b.text for b in buttons] == ["Make Quick Start", "Done"]
    assert all(b.style.flex == 1 for b in buttons)
    # Everything else is in the scrolling part
    inside = walk(form.scroll)
    assert form.args_list in inside and form.env_list in inside
    form.done()


def test_each_section_folds_under_its_switch(proto: ui.Prototype, config: Path) -> None:
    form = proto.open_run_with(row(proto, "top"))
    assert set(form.sections) == {"args", "env"}
    for name, (switch, body) in form.sections.items():
        assert switch.value is True and body.style.display == "pack", name
        assert flip(form, name, False).style.display == "none"
        assert flip(form, name, True).style.display == "pack"
    form.done()


def test_section_titles_count_what_they_hold(proto: ui.Prototype, config: Path) -> None:
    form = proto.open_run_with(row(proto, "top"))
    args_switch = form.sections["args"][0]
    env_switch = form.sections["env"][0]
    assert args_switch.text == "Arguments (0)" and env_switch.text == "Environment (0)"
    form.args += ["one", "two"]
    form.env["GREETING"] = "Hello"
    form.changed()
    assert args_switch.text == "Arguments (2)"
    assert env_switch.text == "Environment (1)"
    form.done()


def test_lists_are_sized_to_their_rows(proto: ui.Prototype, config: Path) -> None:
    """A list can't flex inside a ScrollContainer, so it gets its rows' height."""
    form = proto.open_run_with(row(proto, "top"))
    assert form.args_list.style.display == "none"  # the title says (0)
    form.args += ["one", "two"]
    form.changed()
    assert form.args_list.style.display == "pack"
    assert form.args_list.style.height == 2 * run_with.ROW_HEIGHT
    form.args += [str(n) for n in range(10)]
    form.changed()
    assert form.args_list.style.height == run_with.MOST_ROWS * run_with.ROW_HEIGHT
    form.done()


def test_backups_section_scrolls_with_the_rest_and_starts_folded(
    proto: ui.Prototype, config: Path, docs: Path
) -> None:
    script = docs / "top.py"
    old = script.read_text()
    versions.back_up(script, NOW)
    script.write_text(old + "# newer\n")
    form = proto.open_run_with(row(proto, "top"))
    switches = [w for w in walk(form.scroll) if isinstance(w, toga.Switch)]
    backups = next(s for s in switches if s.text.startswith("Backup versions"))
    assert backups.text == "Backup versions (1)" and backups.value is False
    assert not any(
        isinstance(w, toga.Button) and w.text in ("Restore", "Delete")
        for w in walk(form.content)
    )
    form.done()


def test_no_notes_explain_what_is_discoverable(
    proto: ui.Prototype, config: Path, docs: Path
) -> None:
    """No labels explaining Share, the swipes, or the hidden variables' count."""
    proto.system_env = {"TZ": "UTC"}
    script = docs / "top.py"
    versions.back_up(script, NOW)
    script.write_text("# newer\n")
    form = proto.open_run_with(row(proto, "top"))
    texts = [
        w.text
        for w in walk(form.content)
        if isinstance(w, toga.Label) and w.style.display != "none"
    ]
    assert not [
        t for t in texts if t.startswith(("Share", "Swipe", "No ")) or "hidden" in t
    ]
    form.done()


class Said:
    """Stand-ins for the confirmation and the message."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    async def ask(self, title: str, text: str) -> bool:
        self.asked.append(title)
        return True

    async def tell(self, title: str, text: str) -> None:
        pass


@pytest.fixture
def tool(tmp_path: Path) -> Path:
    path = tmp_path / "tool.py"
    path.write_text("v1")
    versions.back_up(path, NOW)
    path.write_text("v2")
    return path


def section(tool: Path, said: Said) -> run_backups.BackupsSection:
    return run_backups.BackupsSection(tool, ask=said.ask, tell=said.tell)


def test_backup_rows_swipe_left_to_delete_and_right_to_restore(
    tool: Path, app: toga.App
) -> None:
    s = section(tool, Said())
    assert s.list._primary_action == "Delete"  # trailing swipe, shown in red
    assert s.list._secondary_action == "Restore"  # leading swipe
    s.switch.value = True
    s.toggle(s.switch)
    assert s.details.style.display == "pack"
    assert s.list.style.height == run_with.ROW_HEIGHT


def test_swiping_a_backup_asks_then_acts(tool: Path, app: toga.App) -> None:
    said = Said()
    s = section(tool, said)
    s.swipe_restore(s.list, row=s.list.data[0])
    run(app, wait_until_asked(said, 1))
    run(app, settle())
    assert tool.read_text() == "v1" and said.asked == ["Restore"]
    # The restored-over version is kept as another backup
    assert len(versions.list_backups(tool)) == 2
    s.swipe_delete(s.list, row=s.list.data[0])
    run(app, wait_until_asked(said, 2))
    run(app, settle())
    assert said.asked[-1] == "Delete" and len(versions.list_backups(tool)) == 1
    assert len(s.list.data) == 1


def test_a_stale_row_does_nothing(tool: Path, app: toga.App) -> None:
    said = Said()
    s = section(tool, said)
    gone = s.list.data[0]
    s.list.data = []
    s.swipe_delete(s.list, row=gone)
    run(app, settle())
    assert said.asked == [] and len(versions.list_backups(tool)) == 1


async def settle() -> None:
    """Let tasks the handlers started run to the end."""
    import asyncio

    for _ in range(5):
        await asyncio.sleep(0)


async def wait_until_asked(said: Said, count: int) -> None:
    """Wait for the handler's task to ask its question."""
    import asyncio

    for _ in range(50):
        if len(said.asked) >= count:
            return
        await asyncio.sleep(0)
