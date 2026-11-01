"""Render Markdown and wrap HTML for the in-app web views (Help and About).

Kept free of Toga imports so it can be unit tested on desktop. The page's HTML
and CSS live in ``resources/templates/page.html``.
"""

from functools import cache
from pathlib import Path
from string import Template

from markdown import markdown as md

TEMPLATES = Path(__file__).parent / "resources" / "templates"

# Pygments styles for code blocks, chosen for contrast on the page's card colour
LIGHT_STYLE = "default"
DARK_STYLE = "github-dark"


def help_html(markdown_text: str) -> str:
    """Render Help page Markdown, highlighting ```python code with Pygments.

    Unlabelled code blocks are left plain. Without Pygments, code blocks still
    render, just uncoloured.
    """
    try:
        import pygments  # noqa: F401
    except ImportError:
        return md(markdown_text, extensions=["fenced_code"])
    return md(
        markdown_text,
        extensions=["fenced_code", "codehilite"],
        extension_configs={
            "codehilite": {"guess_lang": False, "css_class": "codehilite"}
        },
    )


@cache
def code_css() -> str:
    """Pygments CSS for `.codehilite` blocks: a light style, then a dark one.

    Pygments' own block background is dropped, so code keeps the page's card
    colour (see ``pre`` in page.html). Empty if Pygments isn't available.
    """
    try:
        from pygments.formatters import HtmlFormatter
    except ImportError:
        return ""
    light = HtmlFormatter(style=LIGHT_STYLE).get_style_defs(".codehilite")
    dark = HtmlFormatter(style=DARK_STYLE).get_style_defs(".codehilite")
    reset = ".codehilite { background: none; }"
    return (
        f"{light}\n{reset}\n@media (prefers-color-scheme: dark) {{\n{dark}\n{reset}\n}}"
    )


@cache
def _page_template() -> Template:
    """The page template, read once."""
    return Template((TEMPLATES / "page.html").read_text(encoding="utf-8"))


def html_page(body: str) -> str:
    """Wrap an HTML fragment in the page template used by the in-app web views."""
    return _page_template().substitute(body=body, code_css=code_css())
