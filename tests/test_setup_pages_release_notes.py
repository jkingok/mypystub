"""A newer build's What's New, shown as formatted Markdown, not raw text (#203).

A Release's body is Markdown (see #208), and it comes from GitHub, so it is
rendered as an untrusted README is: raw HTML stays text, unsafe links go.
"""

from mypystub import release_check, setup_pages
from mypystub.maintenance import Health


def notes_html(notes: str) -> str:
    build = release_check.BuildStatus(
        kind="newer",
        running="2026.11.8.1",
        latest="2026.11.9.2",
        url="https://github.com/jkingok/mypystub/releases/tag/2026.11.9.2",
        published="2026-11-09",
        notes=notes,
    )
    return setup_pages.build_notes(Health(None, [], build))


def test_markdown_is_rendered() -> None:
    page = notes_html("### Features\n\n- Logs tab scrolls.\n- **Clear** the log.")
    assert "<h3>Features</h3>" in page
    assert "<li>Logs tab scrolls.</li>" in page
    assert "<strong>Clear</strong>" in page
    assert "<pre>" not in page and "###" not in page


def test_raw_html_and_unsafe_links_are_not_trusted() -> None:
    page = notes_html(
        "<script>alert(1)</script>\n\n[bad](javascript:alert(1)) [ok](https://x.org)"
    )
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "javascript:" not in page
    assert 'href="https://x.org"' in page


def test_an_excerpt_still_renders_as_a_list() -> None:
    body = "\n".join(f"- Item {n} of a long list of changes." for n in range(60))
    page = notes_html(release_check.excerpt(body))
    assert page.count("<li>") >= 10 and "…" in page
