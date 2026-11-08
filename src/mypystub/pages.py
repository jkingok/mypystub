"""Render Markdown and wrap HTML for the in-app web views (Help and About).

Kept free of Toga imports so it can be unit tested on desktop. The page's HTML
and CSS live in ``resources/templates/page.html``.
"""

import html
import re
from functools import cache
from pathlib import Path
from string import Template
from typing import Any
from urllib.parse import urlsplit
from xml.etree.ElementTree import Element

from markdown import Markdown
from markdown import markdown as md
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

TEMPLATES = Path(__file__).parent / "resources" / "templates"

# Pygments styles for code blocks, chosen for contrast on the page's card colour
LIGHT_STYLE = "default"
DARK_STYLE = "github-dark"


# Link schemes a README may use; anything else (javascript:, data:, file:...)
# has its link removed. An empty scheme is a relative link or #anchor.
SAFE_SCHEMES = frozenset({"", "http", "https", "mailto"})


def _markdown_options() -> dict[str, Any]:
    """Extensions for fenced code, highlighted with Pygments when it's there."""
    try:
        import pygments  # noqa: F401
    except ImportError:
        return {"extensions": ["fenced_code"]}
    return {
        "extensions": ["fenced_code", "codehilite"],
        "extension_configs": {
            "codehilite": {"guess_lang": False, "css_class": "codehilite"}
        },
    }


def help_html(markdown_text: str) -> str:
    """Render Help page Markdown, highlighting ```python code with Pygments.

    Unlabelled code blocks are left plain. Without Pygments, code blocks still
    render, just uncoloured.
    """
    return md(markdown_text, **_markdown_options())


def safe_url(url: str) -> bool:
    """Whether a link or image URL from untrusted Markdown may be kept."""
    # Browsers ignore control characters and spaces inside a scheme, so
    # "java\tscript:" must be read as "javascript:"
    cleaned = "".join(ch for ch in url if ch > " ")
    try:
        scheme = urlsplit(cleaned).scheme.lower()
    except ValueError:
        return False
    return scheme in SAFE_SCHEMES


class _SafeLinks(Treeprocessor):
    """Drop link targets and image sources that could run code."""

    def run(self, root: Element) -> None:
        """Remove unsafe ``href`` and ``src`` attributes in place."""
        for element in root.iter():
            for attribute in ("href", "src"):
                value = element.get(attribute)
                if value is not None and not safe_url(value):
                    del element.attrib[attribute]


class _UntrustedMarkdown(Extension):
    """Treat raw HTML as text, and keep only safe links."""

    def extendMarkdown(self, md: Markdown) -> None:
        """Turn off raw HTML blocks and inline tags; add the link filter."""
        md.preprocessors.deregister("html_block")
        md.inlinePatterns.deregister("html")
        md.treeprocessors.register(_SafeLinks(md), "safe_links", 0)


def readme_html(text: str, name: str) -> str:
    """Render a README that came from the user or a download, not the app.

    Markdown READMEs are rendered like the Help page, but raw HTML is shown
    as text and links that could run code are removed. Other READMEs (such
    as ``README.txt``) are shown as preformatted text.
    """
    if not name.lower().endswith((".md", ".markdown")):
        return f"<pre>{html.escape(text)}</pre>"
    options = _markdown_options()
    options["extensions"] = [*options["extensions"], _UntrustedMarkdown()]
    return md(text, **options)


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


# A heading at the very start of a page, and what it says
_LEADING_HEADING = re.compile(r"\s*<h([1-3])>(.*?)</h\1>\s*", re.DOTALL)


def without_title(body: str, title: str) -> str:
    """`body` without its opening heading, if that only repeats `title`.

    A page shown on its own screen already has the title in the window's
    title bar, so the same words again at the top of the page are noise.
    """
    match = _LEADING_HEADING.match(body)
    if match and html.unescape(match.group(2)).strip() == title.strip():
        return body[match.end() :]
    return body
