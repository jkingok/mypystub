"""The paste_to_html example: pasted text saved as an HTML file."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

EXAMPLE = (
    Path(__file__).parent.parent
    / "src/mypystub/resources/examples/claude/paste_to_html.py"
)


@pytest.fixture
def paste() -> ModuleType:
    spec = importlib.util.spec_from_file_location("paste_to_html", EXAMPLE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def answers(monkeypatch: pytest.MonkeyPatch, *replies: str) -> None:
    """input() gives these replies in turn."""
    queue = list(replies)
    monkeypatch.setattr("builtins.input", lambda prompt="": queue.pop(0))


def test_names_end_in_html_and_stay_in_the_folder(paste: ModuleType) -> None:
    assert paste.html_name(" notes ") == "notes.html"
    assert paste.html_name("page.HTM") == "page.HTM"
    assert paste.html_name("../up") == ".._up.html"
    with pytest.raises(SystemExit):
        paste.html_name("  ")


def test_off_ios_the_pasteboard_is_not_read(paste: ModuleType) -> None:
    assert paste.read_pasteboard() is None


def test_typed_text_is_saved(
    paste: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    answers(monkeypatch, "<p>Hi</p>", "<p>there</p>", "", "page")
    paste.main()
    assert (tmp_path / "page.html").read_text() == "<p>Hi</p>\n<p>there</p>"


def test_an_existing_file_is_kept_unless_you_say_so(
    paste: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "page.html").write_text("old")
    monkeypatch.setattr(paste, "read_pasteboard", lambda: "new")
    answers(monkeypatch, "page", "n")
    with pytest.raises(SystemExit, match="Not saved"):
        paste.main()
    assert (tmp_path / "page.html").read_text() == "old"
    answers(monkeypatch, "page", "y")
    paste.main()
    assert (tmp_path / "page.html").read_text() == "new"
