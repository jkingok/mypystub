"""A script's Info page can be built from its text, and is the same page (#189)."""

from pathlib import Path

import pytest

from mypystub import info_pages

SCRIPTS = {
    "plain": "print('hi')\n",
    "docstring": '"""Counts things.\n\nIt counts them well.\n"""\nprint(1)\n',
    "metadata": (
        "# /// script\n# dependencies = ['rich>=13']\n# ///\n"
        '"""Pretty output."""\nprint(1)\n'
    ),
    "syntax error": "def broken(:\n",
    "bad metadata": "# /// script\n# dependencies = [\n# ///\nprint(1)\n",
    "no final newline": "x = 1",
    "empty": "",
}


@pytest.mark.parametrize("source", SCRIPTS.values(), ids=SCRIPTS.keys())
def test_text_and_file_give_the_same_page(tmp_path: Path, source: str) -> None:
    """Building the page from text is identical to building it from the file."""
    path = tmp_path / "tool.py"
    path.write_text(source)
    from_file = info_pages.script_info_html(path, "tool")
    assert info_pages.script_info_from_source(source, "tool", "tool.py") == from_file


def test_the_page_has_the_description_dependencies_and_source() -> None:
    """What the paste preview used to leave out."""
    page = info_pages.script_info_from_source(
        SCRIPTS["metadata"], "pretty", "pretty.py"
    )
    assert "<h1>pretty</h1>" in page and "Pretty output." in page
    assert "Dependencies" in page and "rich&gt;=13" in page
    assert "Script metadata" in page and "pretty.py, 5 lines" in page


def test_a_missing_file_still_says_so(tmp_path: Path) -> None:
    """Reading a file that isn't there is reported, as before."""
    page = info_pages.script_info_html(tmp_path / "gone.py", "gone")
    assert "Couldn't read the script" in page
