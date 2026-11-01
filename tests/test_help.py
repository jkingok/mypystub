"""The in-app Help page renders its Markdown correctly."""

import re
from pathlib import Path

from mypystub import ui

HELP = Path(ui.__file__).parent / "resources" / "templates" / "help.md"


def test_code_blocks_render_as_code_not_headings() -> None:
    """Fenced code blocks stay code; `# comments` inside don't become headings."""
    html = ui.help_html("Intro\n\n```python\n# a comment\nx = 1\n```\n")
    assert "<h1>" not in html
    assert re.search(r"<pre><code[^>]*># a comment\nx = 1\n</code></pre>", html)


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
