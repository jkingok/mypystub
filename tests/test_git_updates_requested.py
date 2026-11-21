"""Reading a git requirement, and the direct_url.json recorded for it (#328)."""

import pytest

from mypystub import git_updates as g


def test_a_github_requirement_with_ref_and_subdirectory() -> None:
    found = g.requested("Thing", "git+https://github.com/o/r.git@v1#subdirectory=pkg")
    assert found == g.GitSource("thing", "https://github.com/o/r.git", "", "v1", "pkg")
    assert found.path == ["o", "r"]


def test_gitlab_groups_nest() -> None:
    found = g.requested("x", "git+https://gitlab.com/group/sub/repo")
    assert found is not None and found.path == ["group", "sub", "repo"]


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/o/r/archive/main.zip",
        "git+https://example.com/o/r",
        "git+ssh://git@github.com/o/r",
        "git+https://github.com/o",
    ],
)
def test_anything_else_is_not_asked_about(url: str) -> None:
    assert g.requested("x", url) is None


def test_pinning_keeps_the_fragment() -> None:
    assert g.at_commit("git+https://github.com/o/r@main#subdirectory=p", "abc") == (
        "git+https://github.com/o/r@abc#subdirectory=p"
    )


def test_direct_url_json_reads_back() -> None:
    source = g.GitSource("x", "https://github.com/o/r", "", "dev", "pkg")
    text = g.direct_url_json(source, "a" * 40)
    assert g.source_from("x", text) == g.GitSource(
        "x", "https://github.com/o/r", "a" * 40, "dev", "pkg"
    )


def test_the_requirement_installs_the_branch_again() -> None:
    source = g.GitSource("x", "https://github.com/o/r", "a" * 40, "dev", "pkg")
    assert g.requirement_for(source) == (
        "x @ git+https://github.com/o/r@dev#subdirectory=pkg"
    )
    plain = g.GitSource("x", "https://github.com/o/r", "a" * 40)
    assert g.requirement_for(plain) == "x @ git+https://github.com/o/r"
