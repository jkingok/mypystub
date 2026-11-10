"""What a pasted file may be called, and which files can be pasted at all.

Skipped where toga_dummy isn't installed, such as on device.
"""

import os
from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import ui
from tests.support_ui import run


def test_a_clash_is_kept_as_a_version_under_the_cleaned_name(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``x.csv.csv`` is written as ``x.csv``, so that is the name that is kept."""
    asked: list[str] = []

    async def ask(title: str, text: str) -> bool:
        asked.append(text)
        return True

    monkeypatch.setattr(proto, "ask", ask)
    (docs / "x.csv").write_text("old")
    source = tmp_path / "copied"
    source.mkdir()
    (source / "x.csv.csv").write_text("new")
    imported = run(app, proto.paste_file(source / "x.csv.csv", docs))
    assert imported.path == docs / "x.csv" and imported.path.read_text() == "new"
    assert asked == []  # nothing is replaced for good, so nothing is asked
    assert imported.previous is not None and imported.previous.read_text() == "old"
    assert not (docs / "x.csv.csv").exists()


@pytest.mark.parametrize("name", ["notes.txt", "NOTES.TXT", "notes.text", "x.txt.txt"])
def test_a_plain_text_file_cannot_be_imported(
    proto: ui.Prototype, tmp_path: Path, name: str
) -> None:
    """The preview says why, and Import stays off."""
    source = tmp_path / name
    source.write_text("just some notes\n")
    _, body, can_import = proto.import_preview("file", str(source))
    assert not can_import
    assert "Plain text files" in body


@pytest.mark.parametrize("name", ["data.csv", "README.md", "config.toml"])
def test_other_files_can_still_be_imported(
    proto: ui.Prototype, tmp_path: Path, name: str
) -> None:
    """Only plain text is turned away."""
    source = tmp_path / name
    source.write_text("content\n")
    _, body, can_import = proto.import_preview("file", str(source))
    assert can_import
    assert "will be copied here" in body
