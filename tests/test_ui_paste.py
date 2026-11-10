"""UI tests for the Paste button.

Skipped where toga_dummy isn't installed, such as on device.
"""

import os
from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import ui
from tests.support_ui import (
    run,
    titles,
)

# Paste (#36)
# ---------------------------------------------------------------------------


def paste(proto: ui.Prototype, app: toga.App) -> None:
    """Show the paste preview, then press Import (when there's something to import)."""
    run(app, proto.handle_paste())
    if proto._pending_import is not None:
        run(app, proto._do_import())


def preview_buttons(app: toga.App) -> list[str]:
    """The buttons on the preview screen currently shown."""
    column = app.main_window.content
    top = column.children[0]
    return [w.text for w in top.children if isinstance(w, toga.Button)]


@pytest.fixture
def pasteboard(monkeypatch: pytest.MonkeyPatch) -> dict:
    """The pasteboard's content, set by each test as ("file", path) or ("text", s)."""
    from mypystub import bridge

    state: dict = {"content": None}

    async def read_pasteboard(into: Path) -> tuple[str, str] | None:
        return state["content"]

    monkeypatch.setattr(bridge, "read_pasteboard", read_pasteboard)
    return state


@pytest.fixture
def source_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A folder outside Documents that pasted files are copied from."""
    return tmp_path_factory.mktemp("pasteboard_source")


@pytest.fixture
def answers(proto: ui.Prototype, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Scripted answers to the paste flow's questions and file-name screen."""
    state: dict = {"yes_no": [], "name": None, "asked": [], "info": []}

    async def ask(title: str, text: str) -> bool:
        state["asked"].append(title)
        return state["yes_no"].pop(0)

    async def ask_text(title: str, label: str, initial: str) -> str | None:
        state["suggested"] = initial
        return state["name"]

    async def info(text: str, title: str | None = None) -> None:
        state["info"].append((title, text))

    monkeypatch.setattr(proto, "ask", ask)
    monkeypatch.setattr(proto, "ask_text", ask_text)
    monkeypatch.setattr(proto, "info", info)
    return state


def test_paste_text_asks_for_a_name_and_adds_a_runnable_script(
    proto: ui.Prototype, app: toga.App, docs: Path, pasteboard: dict, answers: dict
) -> None:
    """Pasted text is assumed to be Python and saved under the name given."""
    pasteboard["content"] = ("text", "print('pasted')\n")
    answers["name"] = "pasted_tool"
    paste(proto, app)
    assert (docs / "pasted_tool.py").read_text() == "print('pasted')\n"
    # The suggestion has no extension: pasted text is always saved as .py
    assert answers["suggested"].startswith("pasted_")
    assert "." not in answers["suggested"]
    assert "pasted_tool" in titles(proto)
    assert answers["info"][-1] == ("Pasted", "Added pasted_tool.py.")


def test_paste_text_can_be_cancelled(
    proto: ui.Prototype, app: toga.App, docs: Path, pasteboard: dict, answers: dict
) -> None:
    """Cancelling the name screen adds nothing."""
    pasteboard["content"] = ("text", "x = 1\n")
    answers["name"] = None
    paste(proto, app)
    assert not (docs / "pasted").exists() and "x" not in titles(proto)
    assert answers["info"] == []


def test_paste_text_over_an_existing_script_keeps_the_old_one_as_a_version(
    proto: ui.Prototype, app: toga.App, docs: Path, pasteboard: dict, answers: dict
) -> None:
    """No question: the new one has the name, the old is kept beside it (#182)."""
    (docs / "top.py").write_text("old")
    pasteboard["content"] = ("text", "new")
    answers["name"] = "top.py"
    paste(proto, app)
    assert answers["asked"] == []
    assert (docs / "top.py").read_text() == "new"
    (older,) = list((docs / "backups").iterdir())
    assert older.read_text() == "old"
    assert "Backup versions" in answers["info"][-1][1]
    assert "top" in titles(proto) and "backups" not in titles(proto)


def test_paste_a_file_keeps_it_as_it_is(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    source_dir: Path,
    pasteboard: dict,
    answers: dict,
) -> None:
    """A copied file is preferred and copied unchanged, with no questions."""
    source = source_dir / "tool.pyz"
    source.write_bytes(b"PK-zipapp")
    pasteboard["content"] = ("file", str(source))
    paste(proto, app)
    assert (docs / "tool.pyz").read_bytes() == b"PK-zipapp"
    assert answers["asked"] == []


def test_paste_an_archive_previews_then_extracts(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    source_dir: Path,
    pasteboard: dict,
    answers: dict,
) -> None:
    """The preview lists the archive's contents; Import extracts into a folder."""
    import zipfile

    source = source_dir / "proj.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("proj/a.py", "print(1)\n")
    pasteboard["content"] = ("file", str(source))
    run(app, proto.handle_paste())
    _, body, _ = proto.import_preview("file", str(source))
    assert "proj" in body  # the top-level folder is listed in the preview
    assert preview_buttons(app) == ["✕ Cancel", "Import"]
    run(app, proto._do_import())
    assert (docs / "proj" / "a.py").exists() and not (docs / "proj.zip").exists()
    assert answers["asked"] == []  # no extract/keep question any more


def test_paste_with_nothing_or_in_examples_says_why(
    proto: ui.Prototype, app: toga.App, docs: Path, pasteboard: dict, answers: dict
) -> None:
    """An empty pasteboard, or the read-only Examples, gets an explanation."""
    run(app, proto.handle_paste())
    assert answers["info"][-1][0] == "Nothing to paste"
    proto.show_category("Examples")
    pasteboard["content"] = ("text", "x")
    run(app, proto.handle_paste())
    assert answers["info"][-1][0] == "Paste" and "Documents" in answers["info"][-1][1]


def test_paste_reports_a_bad_archive(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    source_dir: Path,
    pasteboard: dict,
    answers: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An archive that can't be extracted is an error, not a crash."""
    import zipfile

    source = source_dir / "evil.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("../escape.py", "x")
    errors: list[str] = []

    async def error(text: str, title: str | None = None) -> None:
        errors.append(text)

    monkeypatch.setattr(proto, "error", error)
    pasteboard["content"] = ("file", str(source))
    paste(proto, app)
    assert errors and "unsafe" in errors[0]
    assert not (source_dir.parent / "escape.py").exists()


def test_an_unreadable_archive_cannot_be_imported(
    proto: ui.Prototype, app: toga.App, source_dir: Path, pasteboard: dict
) -> None:
    """The preview says so plainly, without tarfile's errors, and Import is off."""
    source = source_dir / "bad.zip"
    source.write_bytes(b"not a zip at all")
    pasteboard["content"] = ("file", str(source))
    _, body, can_import = proto.import_preview("file", str(source))
    assert not can_import
    assert "can't be read" in body and "method" not in body
    run(app, proto.handle_paste())
    assert not proto.import_button.enabled


def test_preview_shows_source_before_importing(
    proto: ui.Prototype, app: toga.App, docs: Path, pasteboard: dict, answers: dict
) -> None:
    """Pasting text shows its source behind Cancel/Import, and imports nothing yet."""
    pasteboard["content"] = ("text", "print('review me')\n")
    run(app, proto.handle_paste())
    assert preview_buttons(app) == ["✕ Cancel", "Import"]
    assert proto._pending_import is not None
    assert list(docs.glob("pasted*.py")) == []  # not written until Import
    _, body, _ = proto.import_preview("text", "print('review me')\n")
    assert "review me" in body


def test_cancel_discards_without_importing(
    proto: ui.Prototype, app: toga.App, docs: Path, pasteboard: dict, answers: dict
) -> None:
    """Cancel on the preview adds nothing and forgets the pending paste."""
    pasteboard["content"] = ("text", "x = 1\n")
    run(app, proto.handle_paste())
    proto.cancel_import()
    assert proto._pending_import is None
    assert list(docs.glob("pasted*.py")) == []


def test_paste_button_is_for_ios_only(proto: ui.Prototype) -> None:
    """Without a pasteboard to read, the button isn't shown."""
    assert proto.paste_button.text == "Paste"
    assert proto.paste_button.style.display == "none"  # tests run off iOS
