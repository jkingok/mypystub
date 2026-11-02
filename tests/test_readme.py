"""Tests for rendering READMEs, which come from users or downloads (#59)."""

import pytest

from mypystub.pages import help_html, readme_html, safe_url


def test_markdown_renders_like_help() -> None:
    """Headings, lists, links and fenced code render as they do on Help."""
    text = "# Title\n\n- item\n\n[site](https://example.org)\n\n```python\nx = 1\n```\n"
    page = readme_html(text, "README.md")
    assert "<h1>Title</h1>" in page and "<li>item</li>" in page
    assert '<a href="https://example.org">site</a>' in page
    assert 'class="codehilite"' in page or "<code>" in page


def test_raw_html_is_shown_as_text() -> None:
    """Raw HTML blocks and inline tags are escaped, not passed through."""
    page = readme_html(
        "<script>alert(1)</script>\n\nHi <img src=x onerror=alert(1)>\n", "README.md"
    )
    assert "<script>" not in page and "<img" not in page
    assert "&lt;script&gt;" in page


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "JAVASCRIPT:alert(1)",
        "java\tscript:alert(1)",
        "data:text/html,x",
        "file:///etc/passwd",
    ],
)
def test_unsafe_links_lose_their_target(url: str) -> None:
    """Links that could run code, or reach local files, keep their text only."""
    page = readme_html(f"[click]({url})\n\n![pic]({url})\n", "README.md")
    assert "href" not in page and "src" not in page
    assert "click" in page


@pytest.mark.parametrize(
    ("url", "safe"),
    [
        ("https://example.org", True),
        ("http://example.org", True),
        ("mailto:a@example.org", True),
        ("#section", True),
        ("docs/guide.md", True),
        (" javascript:alert(1)", False),
        ("vbscript:x", False),
    ],
)
def test_safe_url(url: str, safe: bool) -> None:
    """Only web, mail and relative links are kept."""
    assert safe_url(url) is safe


def test_plain_text_readmes_are_preformatted() -> None:
    """README.txt and README are shown as text, escaped."""
    assert (
        readme_html("a <b> & c\n", "README.txt") == "<pre>a &lt;b&gt; &amp; c\n</pre>"
    )
    assert readme_html("<i>x</i>", "README").startswith("<pre>&lt;i&gt;")


def test_help_still_allows_its_own_html() -> None:
    """The bundled Help page is trusted, so it isn't filtered."""
    assert "<kbd>" in help_html("Press <kbd>Enter</kbd>.")
