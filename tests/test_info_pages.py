"""Tests for the Info view's HTML report (#99)."""

from pathlib import Path

from mypystub import info_pages
from mypystub.piplike import EntryPoint


def write(path: Path, text: str) -> Path:
    """Create `path` with `text`, making parent folders as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# -- Scripts -------------------------------------------------------------------

SCRIPT = '''"""Fetch the weather.

Uses an API, and prints <b>bold</b> claims.
"""
# /// script
# dependencies = ["httpx"]
# ///

print("<script>alert(1)</script>")
'''


def test_script_page_shows_docstring_dependencies_and_source(tmp_path: Path) -> None:
    """Docstring paragraphs, PEP 723 dependencies, the block, and the source."""
    page = info_pages.script_info_html(write(tmp_path / "w.py", SCRIPT), "Weather")
    assert "<h1>Weather</h1>" in page
    assert "<p>Fetch the weather.</p>" in page
    assert "&lt;b&gt;bold&lt;/b&gt;" in page  # docstrings are text, not HTML
    assert "<h2>Dependencies</h2>" in page and "<code>httpx</code>" in page
    assert "<h2>Script metadata</h2>" in page
    assert "w.py, 9 lines." in page
    assert str(tmp_path) not in page


def test_script_source_is_escaped_with_line_numbers(tmp_path: Path) -> None:
    """Source is highlighted text: tags in it can't run."""
    page = info_pages.script_info_html(write(tmp_path / "w.py", SCRIPT), "w")
    assert "<script>" not in page
    assert "&lt;script&gt;" in page
    assert 'class="linenos"' in page or "   9  " in page


def test_plain_script_has_no_metadata_section(tmp_path: Path) -> None:
    """Only metadata that exists is shown; dependencies say "None"."""
    page = info_pages.script_info_html(write(tmp_path / "p.py", "x = 1\n"), "p")
    assert "Script metadata" not in page
    assert "<h2>Dependencies</h2>\n<p>None.</p>" in page
    assert "p.py, 1 line." in page


def test_long_source_is_folded(tmp_path: Path) -> None:
    """Long files show their first lines; the rest waits in a fold."""
    source = "".join(f"x{n} = {n}\n" for n in range(1, 11))
    page = info_pages.source_html(source, limit=4)
    assert page.count("<details>") == 1
    assert "Show all 10 lines" in page
    head, rest = page.split("<details>")
    assert "x4" in head and "x5" not in head
    assert "x5" in rest and "x10" in rest


def test_broken_scripts_still_get_a_page(tmp_path: Path) -> None:
    """A syntax error is reported; a missing file says it couldn't be read."""
    page = info_pages.script_info_html(write(tmp_path / "b.py", "def (:\n"), "b")
    assert "syntax error on line 1" in page and "<h2>Source</h2>" in page
    missing = info_pages.script_info_html(tmp_path / "gone.py", "gone")
    assert "Couldn't read the script" in missing


# -- Projects ------------------------------------------------------------------

FULL = """
[project]
name = "full"
version = "1.2.3"
description = "Everything <filled> in"
requires-python = ">=3.12"
readme = "README.md"
license = "MIT"
license-files = ["LICENSES/*.txt"]
authors = [{name = "Ada", email = "ada@example.org"}, {name = "Grace"}]
dependencies = ["httpx>=0.27"]

[project.optional-dependencies]
fast = ["orjson"]

[project.urls]
Homepage = "https://example.org"
Evil = "javascript:alert(1)"

[project.scripts]
full = "full.cli:main"
"""


def full_project(tmp_path: Path) -> Path:
    """A project with every piece of metadata the page knows."""
    folder = tmp_path / "full"
    write(folder / "pyproject.toml", FULL)
    write(folder / "README.md", "# Full\n\n<script>alert(1)</script>\n")
    write(folder / "LICENSES" / "MIT.txt", "MIT <licence> text")
    write(folder / "CHANGELOG.md", "## 1.2.3\n\n- [x](javascript:alert(1))\n")
    return folder


def test_project_page_shows_all_metadata(tmp_path: Path) -> None:
    """Details, dependencies, extras, entry points, links, README, licence, log."""
    page = info_pages.project_info_html(full_project(tmp_path), "Full")
    for heading in (
        "Details",
        "Dependencies",
        "Optional dependencies",
        "Entry points",
        "Links",
        "README",
        "Licence",
        "Changelog",
    ):
        assert f"<h2>{heading}</h2>" in page, heading
    assert "<p>Everything &lt;filled&gt; in</p>" in page
    assert "Version: 1.2.3" in page
    assert '<a href="mailto:ada@example.org">Ada &lt;ada@example.org&gt;</a>' in page
    assert "Grace" in page
    assert "<code>httpx&gt;=0.27</code>" in page
    assert "<code>fast</code>: <code>orjson</code>" in page
    assert "<code>full</code>: Console · <code>full.cli:main</code>" in page
    assert '<a href="https://example.org">https://example.org</a>' in page
    assert "<code>MIT</code>" in page and "MIT &lt;licence&gt; text" in page
    assert str(tmp_path) not in page


def test_project_page_is_safe(tmp_path: Path) -> None:
    """No raw HTML or javascript: links from any of the project's files."""
    page = info_pages.project_info_html(full_project(tmp_path), "Full")
    assert "<script>" not in page
    assert 'href="javascript' not in page
    assert "Evil: javascript:alert(1)" in page  # shown as text only


def test_minimal_project_shows_only_what_exists(tmp_path: Path) -> None:
    """No README, licence, links or changelog sections when there are none."""
    folder = tmp_path / "min"
    write(folder / "pyproject.toml", '[project]\nname = "min"\n')
    page = info_pages.project_info_html(folder, "min")
    for heading in ("README", "Licence", "Links", "Changelog", "Entry points"):
        assert f"<h2>{heading}</h2>" not in page, heading
    assert "<h2>Dependencies</h2>\n<p>None.</p>" in page


def test_readme_and_licence_forms(tmp_path: Path) -> None:
    """Inline text tables, file tables, and conventional file names all work."""
    folder = tmp_path / "forms"
    write(
        folder / "pyproject.toml",
        '[project]\nname = "forms"\n'
        'readme = {text = "*hi*", content-type = "text/markdown"}\n'
        'license = {file = "COPYING"}\n',
    )
    write(folder / "COPYING", "GPL text")
    page = info_pages.project_info_html(folder, "forms")
    assert "<em>hi</em>" in page
    assert "<h3>COPYING</h3>" in page and "GPL text" in page

    plain = tmp_path / "plain"
    write(plain / "pyproject.toml", '[project]\nname = "plain"\n')
    write(plain / "readme.txt", "plain <text>")
    write(plain / "LICENSE", "Some licence")
    write(plain / "HISTORY.rst", "History")
    page = info_pages.project_info_html(plain, "plain")
    assert "<pre>plain &lt;text&gt;</pre>" in page
    assert "Some licence" in page and "<pre>History</pre>" in page


def test_files_outside_the_project_are_not_read(tmp_path: Path) -> None:
    """A readme or licence path can't reach outside the project folder."""
    write(tmp_path / "secret.md", "TOP SECRET")
    folder = tmp_path / "sneaky"
    write(
        folder / "pyproject.toml",
        '[project]\nname = "sneaky"\nreadme = "../secret.md"\n'
        'license = {file = "../secret.md"}\nlicense-files = ["../*.md"]\n',
    )
    assert "TOP SECRET" not in info_pages.project_info_html(folder, "sneaky")


def test_entry_point_page(tmp_path: Path) -> None:
    """An entry's page names it and its package, without listing every entry."""
    entry = EntryPoint("full", "full.cli:main", "cli", "console_scripts")
    page = info_pages.project_info_html(
        full_project(tmp_path), "full", entry=entry, show_entries=False
    )
    assert "An entry point of full: <code>full</code>: Console" in page
    assert "<h2>Entry points</h2>" not in page


def test_unreadable_pyproject(tmp_path: Path) -> None:
    """A broken pyproject.toml gets a page that says so."""
    folder = tmp_path / "broken"
    write(folder / "pyproject.toml", "[project\n")
    assert "Couldn't read pyproject.toml" in info_pages.project_info_html(
        folder, "broken"
    )
