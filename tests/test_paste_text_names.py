"""Pasted text is always Python, whatever it was called (#167)."""

from datetime import datetime

import pytest

from mypystub import paste_import

NOW = datetime(2026, 11, 6, 9, 5)


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("notes.txt", "notes.py"),
        ("notes.txt.txt", "notes.py"),
        ("NOTES.TXT", "NOTES.py"),
        ("notes.text", "notes.py"),
        ("notes.txt.py", "notes.py"),
        ("notes.py.txt", "notes.py"),
        ("release 1.2.2", "release 1.2.2.py"),
        ("data.csv", "data.csv.py"),
    ],
)
def test_text_extensions_give_way_to_py(typed: str, expected: str) -> None:
    """A name's plain-text ending isn't kept in front of ``.py``."""
    assert paste_import.clean_filename(typed) == expected


@pytest.mark.parametrize("typed", [".txt", ".py", "..txt", ".text.py"])
def test_a_name_that_is_only_an_extension_is_not_usable(typed: str) -> None:
    """Nothing is left once the extensions go."""
    assert paste_import.clean_filename(typed) is None


def test_the_offered_name_has_no_text_extension() -> None:
    """Text copied as ``notes.txt.txt`` is offered as ``notes``."""
    assert paste_import.suggested_stem("notes.txt.txt", NOW) == "notes"
    assert paste_import.suggested_stem(".txt", NOW) == "pasted_20261106_0905"


@pytest.mark.parametrize("name", ["a.txt", "a.TEXT", "a.txt.txt"])
def test_plain_text_files_are_recognised(name: str) -> None:
    """The check ignores case."""
    assert paste_import.is_plain_text(name)


@pytest.mark.parametrize("name", ["a.py", "a.md", "a.txt.zip", "txt"])
def test_other_files_are_not_plain_text(name: str) -> None:
    """Only the final extension counts."""
    assert not paste_import.is_plain_text(name)
