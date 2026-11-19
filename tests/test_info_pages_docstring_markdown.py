"""Info renders a script's docstring as Markdown, as safely as a README (#288)."""

from mypystub.info_pages import script_info_from_source


def page(docstring: str) -> str:
    """The rendered docstring: the page up to its Source section."""
    html = script_info_from_source(f'"""{docstring}"""\n', "Tool", "tool.py")
    return html.split("<h2>Source</h2>")[0]


def test_markdown_is_rendered() -> None:
    html = page(
        "Counts things.\n\n- one\n- two\n\nUse `count()` or ``count(n)``; "
        "see [the docs](https://example.com) and *emphasis*.\n"
    )
    assert "<ul>" in html and "<li>one</li>" in html
    assert "<code>count()</code>" in html and "<code>count(n)</code>" in html
    assert '<a href="https://example.com">the docs</a>' in html
    assert "<em>emphasis</em>" in html


def test_plain_paragraphs_stay_paragraphs() -> None:
    html = page("First paragraph.\n\nSecond paragraph.\n")
    assert "<p>First paragraph.</p>" in html and "<p>Second paragraph.</p>" in html


def test_raw_html_is_escaped() -> None:
    html = page('Hi <script>alert(1)</script> <img src=x onerror="alert(2)">\n')
    assert "<script>" not in html and "<img" not in html
    assert "&lt;script&gt;" in html


def test_unsafe_links_are_dropped() -> None:
    html = page("[click](javascript:alert(1))\n")
    assert "javascript:" not in html


def test_an_indented_docstring_isnt_a_code_block() -> None:
    """Continuation lines are dedented first, so they read as text, not code."""
    html = page("Title line.\n\n    More text here.\n    ")
    assert "<p>More text here.</p>" in html and "<pre>" not in html
