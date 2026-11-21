"""File names for pasted text that isn't Python (#333)."""

import pytest

from mypystub import paste_import as p
from mypystub import text_kinds as k


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("page", "page.html"),
        ("page.html", "page.html"),
        ("page.html.html", "page.html"),
        ("PAGE.HTML", "PAGE.HTML"),
        ("a/b/../page", "page.html"),
        ("my page", "my page.html"),
        ("notes.txt", "notes.txt.html"),  # another ending is part of the name
    ],
)
def test_a_name_gets_its_kind_s_extension(typed: str, expected: str) -> None:
    assert p.clean_text_name(typed, ".html") == expected


@pytest.mark.parametrize("typed", ["", " ", ".", "..", ".html", "\x00"])
def test_nothing_usable_is_none(typed: str) -> None:
    assert p.clean_text_name(typed, ".html") is None


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("tool.py", "tool.py"),
        ("page.html", "page.html"),
        ("README.md", "README.md"),
        ("data.json", "data.json"),
        ("book.ipynb", "book.ipynb"),
        ("notes", "notes.txt"),  # no ending: plain text
        ("notes.docx", "notes.docx.txt"),
    ],
)
def test_when_asked_the_typed_ending_decides(typed: str, expected: str) -> None:
    assert p.clean_text_name(typed, ".txt", k.EXTENSIONS) == expected


def test_python_naming_is_unchanged() -> None:
    assert p.clean_filename("tool") == "tool.py"
    assert p.clean_filename("notes.txt") == "notes.py"
