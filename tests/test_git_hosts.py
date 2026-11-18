"""git+https requirements on GitHub, GitLab and Bitbucket, as archives (#286)."""

import pytest

from mypystub import git_hosts


@pytest.mark.parametrize(
    ("url", "archive"),
    [
        # GitHub
        ("git+https://github.com/o/r", "https://github.com/o/r/archive/HEAD.zip"),
        ("git+https://github.com/o/r.git", "https://github.com/o/r/archive/HEAD.zip"),
        (
            "git+https://github.com/o/r.git@v1.2",
            "https://github.com/o/r/archive/v1.2.zip",
        ),
        (
            "git+https://www.github.com/o/r@main#subdirectory=pkg",
            "https://github.com/o/r/archive/main.zip#subdirectory=pkg",
        ),
        (
            "git+https://github.com/o/r@feature/x#egg=r",
            "https://github.com/o/r/archive/feature/x.zip#egg=r",
        ),
        ("git+http://github.com/o/r", "https://github.com/o/r/archive/HEAD.zip"),
        # GitLab, including nested groups
        (
            "git+https://gitlab.com/g/r.git@v2",
            "https://gitlab.com/g/r/-/archive/v2/r-v2.zip",
        ),
        (
            "git+https://gitlab.com/g/sub/r",
            "https://gitlab.com/g/sub/r/-/archive/HEAD/r-HEAD.zip",
        ),
        # Bitbucket
        (
            "git+https://bitbucket.org/w/tatogalib.git@1.0",
            "https://bitbucket.org/w/tatogalib/get/1.0.zip",
        ),
        (
            "git+https://user@bitbucket.org/w/r",
            "https://bitbucket.org/w/r/get/HEAD.zip",
        ),
    ],
)
def test_pip_git_urls_become_archive_urls(url: str, archive: str) -> None:
    assert git_hosts.archive_url(url) == archive


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/o/r",  # a page: pip can't install it
        "https://github.com/o/r/archive/v1.zip",  # already an archive
        "git+ssh://git@github.com/o/r.git",
        "git+https://example.org/o/r.git",
        "git+https://github.com/o",
        "git+https://github.com/o/r/extra",
        "git+https://bitbucket.org/w",
        "git+https://gitlab.com/r",
    ],
)
def test_other_urls_have_no_archive(url: str) -> None:
    assert git_hosts.archive_url(url) is None


@pytest.mark.parametrize(
    ("url", "suggestion"),
    [
        ("https://github.com/o/r", "git+https://github.com/o/r"),
        ("https://github.com/o/r.git", "git+https://github.com/o/r"),
        ("https://github.com/o/r/tree/v1", "git+https://github.com/o/r@v1"),
        (
            "https://github.com/o/r/tree/feature/x#subdirectory=p",
            "git+https://github.com/o/r@feature/x#subdirectory=p",
        ),
        ("https://gitlab.com/g/sub/r", "git+https://gitlab.com/g/sub/r"),
        ("https://gitlab.com/g/r/-/tree/v2", "git+https://gitlab.com/g/r@v2"),
        ("https://bitbucket.org/w/r", "git+https://bitbucket.org/w/r"),
        ("https://bitbucket.org/w/r/src/v3", "git+https://bitbucket.org/w/r@v3"),
        (  # tatogalib's page, as the browser shows it
            "https://bitbucket.org/TomArn/tatogalib/src/main/",
            "git+https://bitbucket.org/TomArn/tatogalib@main",
        ),
    ],
)
def test_a_page_suggests_the_pip_form(url: str, suggestion: str) -> None:
    assert git_hosts.page_suggestion(url) == suggestion
    # ... and that form is one the installer takes
    assert git_hosts.archive_url(suggestion) is not None


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/o",
        "https://github.com/o/r/issues/1",
        "https://github.com/o/r/blob/main/x.py",
        "https://github.com/o/r/archive/v1.zip",
        "https://gitlab.com/g/r/-/archive/v2/r-v2.zip",
        "https://gitlab.com/g/r/-/issues/3",
        "https://bitbucket.org/w/r/get/v1.zip",
        "https://example.com/github.com/o/r",
        "git+https://github.com/o/r",
    ],
)
def test_other_urls_are_not_pages(url: str) -> None:
    assert git_hosts.page_suggestion(url) is None
