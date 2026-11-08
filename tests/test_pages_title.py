"""A page on its own screen doesn't repeat the window's title as its heading."""

import pytest

from mypystub.pages import without_title


@pytest.mark.parametrize(
    ("body", "title", "expected"),
    [
        ("<h1>top</h1>\n<p>Hi</p>", "top", "<p>Hi</p>"),
        ("<h2>Packages</h2><h3>Python</h3>", "Packages", "<h3>Python</h3>"),
        ("<h1>Tom &amp; Jerry</h1><p>x</p>", "Tom & Jerry", "<p>x</p>"),
        ("<h1>demo-project</h1><p>x</p>", "demo_project.zip", None),
        ("<p>Intro</p><h1>top</h1>", "top", None),
        ("<h4>top</h4><p>x</p>", "top", None),
    ],
)
def test_only_an_opening_heading_that_repeats_the_title_goes(
    body: str, title: str, expected: str | None
) -> None:
    """Different words, a heading further down, or a small one: kept."""
    assert without_title(body, title) == (body if expected is None else expected)
