"""The in-app Help page renders its Markdown correctly."""

import re
import sys
from pathlib import Path

import pytest

from mypystub import pages, ui

HELP = Path(ui.__file__).parent / "resources" / "templates" / "help.md"


def test_code_blocks_render_as_code_not_headings() -> None:
    """Fenced code blocks stay code; `# comments` inside don't become headings."""
    html = ui.help_html("Intro\n\n```python\n# a comment\nx = 1\n```\n")
    assert "<h1>" not in html
    assert "# a comment" in html and "<pre>" in html


def test_python_blocks_are_syntax_highlighted() -> None:
    """```python blocks get Pygments token markup inside a codehilite block (#85)."""
    html = pages.help_html("```python\ndef f():\n    return 1  # one\n```\n")
    assert 'class="codehilite"' in html
    assert '<span class="k">def</span>' in html
    assert '<span class="c1"># one</span>' in html


def test_unlabelled_blocks_stay_plain() -> None:
    """Without a language, code isn't guessed at or coloured."""
    html = pages.help_html("```\ndef f(): pass\n```\n")
    assert '<span class="k">' not in html
    assert "def f(): pass" in html


def test_falls_back_without_pygments(monkeypatch: pytest.MonkeyPatch) -> None:
    """If Pygments can't be imported, code blocks still render, uncoloured."""
    monkeypatch.setitem(sys.modules, "pygments", None)
    html = pages.help_html("```python\n# a comment\nx = 1\n```\n")
    assert re.search(r"<pre><code[^>]*># a comment\nx = 1\n</code></pre>", html)


def test_page_template_has_light_and_dark_code_styles() -> None:
    """The page carries highlight colours for both appearances."""
    page = pages.html_page("<p>hello</p>")
    assert "<p>hello</p>" in page
    assert ".codehilite .k" in page
    dark = page[page.index("@media (prefers-color-scheme: dark)") :]
    assert ".codehilite .k" in dark
    assert "${" not in page  # every placeholder was filled


def test_page_template_lives_in_resources() -> None:
    """The HTML and CSS live in a template file, not in the Python source."""
    template = Path(pages.__file__).parent / "resources" / "templates" / "page.html"
    assert "${body}" in template.read_text(encoding="utf-8")
    assert "<style>" not in Path(ui.__file__).read_text(encoding="utf-8")


def test_bundled_help_has_only_real_headings() -> None:
    """Every heading in help.md is one the author wrote, none from code."""
    html = ui.help_html(HELP.read_text(encoding="utf-8"))
    written = re.findall(
        r"^#+ (.+)$", strip_fences(HELP.read_text(encoding="utf-8")), re.MULTILINE
    )
    rendered = re.findall(r"<h\d>(.*?)</h\d>", html)
    assert rendered == written


def strip_fences(text: str) -> str:
    """Remove fenced code blocks, to list the headings the author wrote."""
    return re.sub(r"^```.*?^```$", "", text, flags=re.MULTILINE | re.DOTALL)
