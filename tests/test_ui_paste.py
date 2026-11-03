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


@pytest.fixture
def pasteboard(monkeypatch: pytest.MonkeyPatch) -> dict:
    """The pasteboard's content, set by each test as ("file", path) or ("text", s)."""
    from mypystub import bridge

    state: dict = {"content": None}
    monkeypatch.setattr(bridge, "read_pasteboard", lambda: state["content"])
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
    run(app, proto.handle_paste())
    assert (docs / "pasted_tool.py").read_text() == "print('pasted')\n"
    assert answers["suggested"].startswith("pasted_") and answers["suggested"].endswith(
        ".py"
    )
    assert "pasted_tool" in titles(proto)
    assert answers["info"][-1] == ("Pasted", "Added pasted_tool.py.")


def test_paste_text_can_be_cancelled(
    proto: ui.Prototype, app: toga.App, docs: Path, pasteboard: dict, answers: dict
) -> None:
    """Cancelling the name screen adds nothing."""
    pasteboard["content"] = ("text", "x = 1\n")
    answers["name"] = None
    run(app, proto.handle_paste())
    assert not (docs / "pasted").exists() and "x" not in titles(proto)
    assert answers["info"] == []


def test_paste_text_does_not_overwrite_unless_told(
    proto: ui.Prototype, app: toga.App, docs: Path, pasteboard: dict, answers: dict
) -> None:
    """A clash asks; No keeps both with an incrementing name."""
    (docs / "top.py").write_text("old")
    pasteboard["content"] = ("text", "new")
    answers["name"] = "top.py"
    answers["yes_no"] = [False]
    run(app, proto.handle_paste())
    assert (docs / "top.py").read_text() == "old"
    assert (docs / "top_2.py").read_text() == "new"
    answers["yes_no"] = [True]
    run(app, proto.handle_paste())
    assert (docs / "top.py").read_text() == "new"


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
    run(app, proto.handle_paste())
    assert (docs / "tool.pyz").read_bytes() == b"PK-zipapp"
    assert answers["asked"] == []


def test_paste_an_archive_asks_whether_to_extract(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    source_dir: Path,
    pasteboard: dict,
    answers: dict,
) -> None:
    """Yes extracts into one folder; No keeps the archive as it is."""
    import zipfile

    source = source_dir / "proj.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("proj/a.py", "print(1)\n")
    pasteboard["content"] = ("file", str(source))
    answers["yes_no"] = [True]
    run(app, proto.handle_paste())
    assert (docs / "proj" / "a.py").exists() and not (docs / "proj.zip").exists()
    assert answers["asked"] == ["Extract archive?"]
    answers["yes_no"] = [False]
    run(app, proto.handle_paste())
    assert (docs / "proj.zip").exists()


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
    answers["yes_no"] = [True]
    run(app, proto.handle_paste())
    assert errors and "unsafe" in errors[0]
    assert not (source_dir.parent / "escape.py").exists()


def test_paste_button_is_for_ios_only(proto: ui.Prototype) -> None:
    """Without a pasteboard to read, the button isn't shown."""
    assert proto.paste_button.text == "Paste"
    assert proto.paste_button.style.display == "none"  # tests run off iOS
