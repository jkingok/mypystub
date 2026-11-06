"""Tests for recognising URL and git requirements (#169, part 1)."""

import pytest
from packaging.requirements import Requirement

from mypystub import direct_refs


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        ("https://host/p/foo-1.0-py3-none-any.whl", "wheel"),
        ("https://host/p/foo-1.0-py3-none-any.whl#sha256=ab12", "wheel"),
        ("https://host/p/foo-1.0.tar.gz", "archive"),
        ("https://host/p/foo-1.0.zip", "archive"),
        ("https://github.com/o/r/archive/refs/tags/v1.zip#subdirectory=pkg", "archive"),
        ("git+https://github.com/o/r.git@v1", "git+https"),
        ("git+https://github.com/o/r.git@v1#subdirectory=pkg", "git+https"),
        ("git+ssh://git@github.com/o/r.git", "git+ssh"),
        ("git+file:///tmp/r", "git"),
        ("file:///tmp/foo.whl", "file"),
        ("https://example.com/download", "other"),
    ],
)
def test_kind_of(url: str, kind: str) -> None:
    """A URL is classified by its scheme and file name."""
    assert direct_refs.kind_of(url) == kind


def test_a_plain_name_is_fine() -> None:
    """Names, versions, extras and markers need no check."""
    for text in ("requests", "requests>=2.0", "rich[jupyter]", "x; python_version>'3'"):
        assert direct_refs.unsupported_message(Requirement(text)) is None


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("foo @ https://host/foo-1.0.tar.gz", "source archive"),
        ("foo @ git+https://github.com/o/r.git@v1", "git repository"),
        ("foo @ git+ssh://git@github.com/o/r.git", "SSH"),
        ("foo @ file:///tmp/foo.whl", "local file"),
    ],
)
def test_url_requirements_are_refused_with_a_reason(text: str, fragment: str) -> None:
    """Each kind says what isn't supported, and offers the PyPI name."""
    message = direct_refs.unsupported_message(Requirement(text))
    assert message is not None
    assert fragment in message
    assert text in message
    assert "Ask for foo by name" in message
