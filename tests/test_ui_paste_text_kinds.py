"""Pasted text is saved by what it is, not always as Python (#333).

Skipped where toga_dummy isn't installed, such as on device.
"""

import os
from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import bridge, ui
from tests.support_ui import run

PAGE = "<!DOCTYPE html>\n<html><head><title>Hi</title></head><body>x</body></html>\n"
PROSE = "Just some words about my day.\n"


@pytest.fixture
def flow(proto: ui.Prototype, monkeypatch: pytest.MonkeyPatch) -> dict:
    """The pasteboard's text, the name typed, and what was asked."""
    state: dict = {"text": "", "name": "", "labels": [], "initial": []}

    async def read_pasteboard(into: Path) -> tuple[str, str]:
        return ("text", state["text"])

    async def ask_text(title: str, label: str, initial: str) -> str | None:
        state["labels"].append(label)
        state["initial"].append(initial)
        return state["name"]

    async def info(text: str, title: str | None = None) -> None:
        state["info"] = text

    monkeypatch.setattr(bridge, "read_pasteboard", read_pasteboard)
    monkeypatch.setattr(proto, "ask_text", ask_text)
    monkeypatch.setattr(proto, "info", info)
    return state


def paste(proto: ui.Prototype, app: toga.App) -> None:
    run(app, proto.handle_paste())
    if proto._pending_import is not None:
        run(app, proto._do_import())


def test_a_web_page_is_saved_as_html(
    proto: ui.Prototype, app: toga.App, docs: Path, flow: dict
) -> None:
    flow.update(text=PAGE, name="my page")
    paste(proto, app)
    assert (docs / "my page.html").read_text() == PAGE
    assert not list(docs.glob("my page*.py"))
    assert flow["labels"] == ["Name for the pasted text (saved as .html)"]
    assert "." not in flow["initial"][0]
    assert flow["info"] == "Added my page.html."


def test_python_is_unchanged(
    proto: ui.Prototype, app: toga.App, docs: Path, flow: dict
) -> None:
    flow.update(text="import os\nprint(os.getcwd())\n", name="tool")
    paste(proto, app)
    assert (docs / "tool.py").is_file()
    assert flow["labels"] == ["Name for the pasted code (saved as .py)"]


def test_markdown_and_json_keep_their_own_endings(
    proto: ui.Prototype, app: toga.App, docs: Path, flow: dict
) -> None:
    flow.update(text="# Notes\n\n- one\n- two\n", name="notes")
    paste(proto, app)
    assert (docs / "notes.md").is_file()
    flow.update(text='{"a": 1}', name="data")
    paste(proto, app)
    assert (docs / "data.json").is_file()


def test_unsure_text_asks_and_the_typed_ending_decides(
    proto: ui.Prototype, app: toga.App, docs: Path, flow: dict
) -> None:
    flow.update(text=PROSE, name="story.md")
    paste(proto, app)
    assert (docs / "story.md").read_text() == PROSE
    assert flow["labels"][0].startswith("Name it, ending in .py, .html, .md")


def test_unsure_text_with_no_ending_is_saved_as_text(
    proto: ui.Prototype, app: toga.App, docs: Path, flow: dict
) -> None:
    flow.update(text=PROSE, name="diary")
    paste(proto, app)
    assert (docs / "diary.txt").read_text() == PROSE
    assert not (docs / "diary.py").exists()


def test_cancelling_the_name_adds_nothing(
    proto: ui.Prototype, app: toga.App, docs: Path, flow: dict
) -> None:
    flow["text"] = PAGE

    async def cancel(title: str, label: str, initial: str) -> None:
        return None

    proto.ask_text = cancel  # type: ignore[method-assign]
    paste(proto, app)
    assert not list(docs.glob("*.html"))


def test_the_preview_says_what_it_looks_like(proto: ui.Prototype, flow: dict) -> None:
    proto._kind_known = False
    title, body, can_import = proto.import_preview("text", PAGE)
    assert can_import and title == "Paste"
    assert "This looks like a web page" in body
    assert ".html</code>, not as a Python script" in body
    assert "&lt;!DOCTYPE html&gt;" in body  # an excerpt, escaped


def test_the_preview_of_unsure_text_says_so(proto: ui.Prototype, flow: dict) -> None:
    proto._kind_known = False
    _, body, can_import = proto.import_preview("text", PROSE)
    assert can_import
    assert "can't tell what kind of text this is" in body
    assert "Just some words" in body


def test_a_long_paste_is_cut_in_the_preview(proto: ui.Prototype, flow: dict) -> None:
    proto._kind_known = False
    long_page = PAGE + "\n".join(f"<p>{n}</p>" for n in range(500))
    _, body, _ = proto.import_preview("text", long_page)
    assert "&lt;p&gt;10&lt;/p&gt;" in body  # escaped, near the top
    assert "&lt;p&gt;400&lt;/p&gt;" not in body and "…" in body


def test_a_second_paste_is_looked_at_again(
    proto: ui.Prototype, app: toga.App, docs: Path, flow: dict
) -> None:
    flow.update(text=PAGE, name="one")
    paste(proto, app)
    flow.update(text="import os\nprint(1)\n", name="two")
    paste(proto, app)
    assert (docs / "one.html").is_file() and (docs / "two.py").is_file()
