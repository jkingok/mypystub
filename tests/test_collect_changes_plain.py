"""Plain-text notes for TestFlight and Firebase: Markdown stripped (#256)."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "collect_changes.py"


def load():
    spec = importlib.util.spec_from_file_location("collect_changes", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WHATS_NEW = """# What's New

## 2026.11.13.1 (2026-11-13)

### New

- About shows the **branch** and `commit` of a build.

### Fixed

- On Android, **Open Documents in Files** works; see [the guide](https://example.test/x) &amp; \\*more\\*.
"""


def test_markdown_is_stripped_from_the_text_notes() -> None:
    notes = load().notes_for(WHATS_NEW, "2026.11.13.1")
    assert notes == (
        "New:\n"
        "• About shows the branch and commit of a build.\n"
        "\n"
        "Fixed:\n"
        "• On Android, Open Documents in Files works; see the guide & *more*."
    )


def test_the_release_notes_keep_their_markdown() -> None:
    notes = load().release_notes_for(WHATS_NEW, "2026.11.13.1")
    assert "**branch**" in notes and "[the guide](https://example.test/x)" in notes


def test_plain_collapses_lines_and_spaces() -> None:
    assert load().plain("one\n  two   *three*") == "one two three"
