"""UI tests for the row of buttons above the list: New Folder and Paste.

Skipped where toga_dummy isn't installed, such as on device.
"""

import os
import zipfile
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import ui
from tests.support_ui import row, run, tap, titles

PYPROJECT = """
[project]
name = "tools"
description = "Some tools"

[project.scripts]
one = "tools.cli:one"
two = "tools.cli:two"
"""


def write_project(docs: Path) -> None:
    """A project folder with two entry points, so it opens like a folder."""
    package = docs / "tools" / "src" / "tools"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "cli.py").write_text("def one(): print(1)\n\ndef two(): print(2)\n")
    (docs / "tools" / "pyproject.toml").write_text(PYPROJECT)


def write_zipapp(path: Path) -> None:
    """A zipapp with two entry points, so it opens like a folder."""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("__main__.py", "print('main')\n")
        archive.writestr("zt/__init__.py", "")
        archive.writestr("zt/cli.py", "def one(): print(1)\n\ndef two(): print(2)\n")
        archive.writestr(
            "zt-1.dist-info/METADATA", "Metadata-Version: 2.1\nName: zt\nVersion: 1\n"
        )
        archive.writestr(
            "zt-1.dist-info/entry_points.txt",
            "[console_scripts]\none = zt.cli:one\ntwo = zt.cli:two\n",
        )


def enabled(p: ui.Prototype) -> tuple[bool, bool]:
    """Whether Paste and New Folder are enabled."""
    return p.paste_button.enabled, p.new_folder_button.enabled


@pytest.fixture
def names(proto: ui.Prototype, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The name screen, scripted: `answers` are typed in turn (None cancels)."""
    state: dict[str, Any] = {"answers": [], "initials": []}

    async def ask_text(title: str, label: str, initial: str) -> str | None:
        state["initials"].append(initial)
        return state["answers"].pop(0)

    monkeypatch.setattr(proto, "ask_text", ask_text)
    return state


def test_both_buttons_share_the_row_equally(proto: ui.Prototype) -> None:
    """Flex, not the text's width, sizes them, so a label can't be squeezed."""
    assert proto.paste_button.parent is proto.new_folder_button.parent
    assert proto.paste_button.parent.children == [
        proto.new_folder_button,
        proto.paste_button,
    ]
    assert proto.paste_button.style.flex == proto.new_folder_button.style.flex == 1
    assert proto.new_folder_button.text == "New Folder"


def test_buttons_follow_the_list_to_every_place(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On only where things can be added: Documents and plain folders in it."""
    write_project(docs)
    write_zipapp(docs / "zt.pyz")
    proto.reload_menu(proto.script_list)

    def go(title: str) -> None:
        tap(proto, title, monkeypatch, app)

    assert enabled(proto) == (True, True)  # Documents
    go("a")
    assert enabled(proto) == (True, True)  # a folder in it
    go("..")
    go("tools")
    assert titles(proto) == ["..", "one", "two"]
    assert enabled(proto) == (False, False)  # inside a project
    go("..")
    assert enabled(proto) == (True, True)
    go("zt")
    assert titles(proto) == ["..", "one", "two"]
    assert enabled(proto) == (False, False)  # inside a zipapp
    go("..")
    assert enabled(proto) == (True, True)
    go("..")
    assert titles(proto) == ["Examples", "Documents"]
    assert enabled(proto) == (False, False)  # the top
    go("Examples")
    assert enabled(proto) == (False, False)  # read-only
    go("..")
    go("Documents")
    assert enabled(proto) == (True, True)


def test_a_refresh_checks_again(proto: ui.Prototype) -> None:
    """Pulling the list to refresh goes through the same place."""
    proto.show_category("Examples")
    proto.script_list.on_refresh()
    assert enabled(proto) == (False, False)
    proto.show_category("Documents")
    proto.script_list.on_refresh()
    assert enabled(proto) == (True, True)


def test_new_folder_is_made_where_you_are(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    names: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In Documents, then in a folder: each goes in the folder being browsed."""
    names["answers"] = ["Fresh"]
    run(app, proto.handle_new_folder())
    assert (docs / "Fresh").is_dir()
    assert "Fresh" in titles(proto) and row(proto, "Fresh").subtitle == "🪣 Empty"

    tap(proto, "a", monkeypatch, app)
    names["answers"] = ["Inner"]
    run(app, proto.handle_new_folder())
    assert (docs / "a" / "Inner").is_dir() and not (docs / "Inner").exists()
    assert "Inner" in titles(proto)


def test_new_folder_asks_again_for_a_name_that_cant_be_used(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    names: dict[str, Any],
    messages: list[tuple],
) -> None:
    """Empty, hidden and taken names each say why, and keep the typing."""
    (docs / "taken").mkdir()
    (docs / "taken" / "keep.py").write_text("x")
    names["answers"] = ["", ".hidden", "taken", "good"]
    run(app, proto.handle_new_folder())
    assert [text for _, text in messages] == [
        "Enter a name for the folder.",
        "A name starting with a dot would be hidden from the list.",
        "taken already exists here.",
    ]
    assert names["initials"] == ["", "", ".hidden", "taken"]
    assert (docs / "good").is_dir()
    assert (docs / "taken" / "keep.py").read_text() == "x"
    assert not (docs / ".hidden").exists()


def test_new_folder_can_be_cancelled(
    proto: ui.Prototype, app: toga.App, docs: Path, names: dict[str, Any]
) -> None:
    """Cancelling the name screen makes nothing."""
    before = sorted(path.name for path in docs.iterdir())
    names["answers"] = [None]
    run(app, proto.handle_new_folder())
    assert sorted(path.name for path in docs.iterdir()) == before


def test_new_folder_and_paste_refuse_where_they_cant_work(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    names: dict[str, Any],
    messages: list[tuple],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If called anyway at the top or in Examples, they explain and do nothing."""
    before = sorted(path.name for path in docs.iterdir())
    tap(proto, "..", monkeypatch, app)  # the top
    run(app, proto.handle_new_folder())
    assert messages[-1][0] == "New Folder"
    tap(proto, "Examples", monkeypatch, app)
    run(app, proto.handle_new_folder())
    assert messages[-1][0] == "New Folder" and len(messages) == 2
    assert names["initials"] == []  # never asked for a name
    assert sorted(path.name for path in docs.iterdir()) == before


def test_paste_goes_into_the_folder_being_browsed(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    names: dict[str, Any],
    messages: list[tuple],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pasting inside a folder adds the file there, not in Documents."""
    from mypystub import bridge

    async def read_pasteboard(into: Path) -> tuple[str, str]:
        return ("text", "print(1)\n")

    monkeypatch.setattr(bridge, "read_pasteboard", read_pasteboard)
    tap(proto, "a", monkeypatch, app)
    names["answers"] = ["pasted"]
    run(app, proto.handle_paste())
    assert (docs / "a" / "pasted.py").read_text() == "print(1)\n"
    assert not (docs / "pasted.py").exists()
    assert "pasted" in titles(proto)
