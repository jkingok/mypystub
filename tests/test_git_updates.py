"""Updates for packages installed from git: direct_url.json and the hosts (#328)."""

import json

import httpx2
import pytest

from mypystub import git_updates as g
from mypystub.maintenance import MaintenanceError

OLD, NEW = "a" * 40, "b" * 40


def direct_url(url: str, commit: str = OLD, **extra: object) -> str:
    vcs = {"vcs": "git", "commit_id": commit, **extra}
    return json.dumps({"url": url, "vcs_info": vcs})


def source(url: str, ref: str | None = None, name: str = "pkg") -> g.GitSource:
    return g.GitSource(name, url, OLD, ref)


def test_a_git_install_is_read_from_direct_url_json() -> None:
    text = json.dumps(
        {
            "url": "https://github.com/beeware/toga.git",
            "vcs_info": {"vcs": "git", "commit_id": OLD, "requested_revision": "main"},
            "subdirectory": "core",
        }
    )
    found = g.source_from("Toga_Core", text)
    assert found == g.GitSource(
        "toga-core", "https://github.com/beeware/toga.git", OLD, "main", "core"
    )
    assert found.host == "github.com" and found.path == ["beeware", "toga"]


@pytest.mark.parametrize(
    "text",
    [
        None,
        "not json",
        json.dumps({"url": "https://x/y.whl", "archive_info": {}}),
        json.dumps({"url": "file:///src", "dir_info": {"editable": True}}),
        json.dumps({"url": "https://hg.example/r", "vcs_info": {"vcs": "hg"}}),
    ],
)
def test_anything_else_is_not_a_git_source(text: str | None) -> None:
    assert g.source_from("pkg", text) is None


def test_a_commit_pin_can_not_move() -> None:
    assert source("https://github.com/o/r", ref=OLD).pinned
    assert not source("https://github.com/o/r", ref="v1.0").pinned
    assert not source("https://github.com/o/r").pinned


def answering(routes: dict[str, str]) -> tuple[httpx2.Client, list[httpx2.Request]]:
    """A client answering known URLs with their text, and 404 otherwise."""
    asked: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        asked.append(request)
        text = routes.get(str(request.url))
        return httpx2.Response(200, text=text) if text else httpx2.Response(404)

    return httpx2.Client(transport=httpx2.MockTransport(handler)), asked


def test_github_is_asked_for_the_branch_head_as_plain_text() -> None:
    client, asked = answering(
        {"https://api.github.com/repos/o/r/commits/HEAD": NEW + "\n"}
    )
    assert g.latest_commit(client, source("https://github.com/o/r.git")) == NEW
    assert asked[0].headers["Accept"] == g.GITHUB_SHA


def test_gitlab_finds_the_default_branch_first() -> None:
    project = "https://gitlab.com/api/v4/projects/group%2Fsub%2Frepo"
    client, _ = answering(
        {
            project: json.dumps({"default_branch": "trunk"}),
            f"{project}/repository/commits/trunk": json.dumps({"id": NEW}),
        }
    )
    assert g.latest_commit(client, source("https://gitlab.com/group/sub/repo")) == NEW


def test_bitbucket_follows_the_named_branch() -> None:
    client, _ = answering(
        {
            "https://api.bitbucket.org/2.0/repositories/w/r/commit/dev": json.dumps(
                {"hash": NEW}
            )
        }
    )
    found = g.latest_commit(client, source("https://bitbucket.org/w/r", ref="dev"))
    assert found == NEW


def test_an_unknown_host_is_not_asked() -> None:
    client, asked = answering({})
    assert g.latest_commit(client, source("https://example.com/o/r")) is None
    assert not asked


def test_compare_links_for_each_host() -> None:
    assert g.compare_url(source("https://github.com/o/r.git"), NEW) == (
        f"https://github.com/o/r/compare/{OLD}...{NEW}"
    )
    assert g.compare_url(source("https://gitlab.com/g/r"), NEW) == (
        f"https://gitlab.com/g/r/-/compare/{OLD}...{NEW}"
    )
    assert "bitbucket.org/w/r/branches/compare/" in str(
        g.compare_url(source("https://bitbucket.org/w/r"), NEW)
    )


def test_packages_from_one_repository_share_a_request() -> None:
    client, asked = answering(
        {
            "https://api.github.com/repos/beeware/toga/commits/HEAD": NEW,
            "https://api.github.com/repos/beeware/toga-console/commits/HEAD": OLD,
        }
    )
    toga = "https://github.com/beeware/toga.git"
    sources = {
        "toga-core": source(toga, name="toga-core"),
        "travertino": source(toga, name="travertino"),
        "toga-console": source(
            "https://github.com/beeware/toga-console", name="toga-console"
        ),
        "pinned": g.GitSource("pinned", "https://github.com/o/p", OLD, OLD),
    }
    checked: list[str] = []
    updates = g.find_git_updates(
        client, sources, critical={"toga-core"}, on_check=checked.append
    )
    assert [u.name for u in updates] == ["toga-core", "travertino"]
    assert len(asked) == 2  # toga once, toga-console once, the pin never
    assert checked == sorted(sources)
    assert updates[0].critical and not updates[1].critical
    assert updates[0].line() == (
        "toga-core: newer commits on the default branch (aaaaaaa → bbbbbbb)"
        " (app-critical)"
    )


def test_a_host_that_can_not_be_reached_fails_the_check() -> None:
    def offline(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("offline", request=request)

    client = httpx2.Client(transport=httpx2.MockTransport(offline))
    with pytest.raises(MaintenanceError, match="api.github.com"):
        g.find_git_updates(client, {"pkg": source("https://github.com/o/r")})


def test_this_environment_s_git_packages_are_found() -> None:
    """The dev environment takes Toga from git, as the app does."""
    found = g.git_sources()
    assert all(s.commit for s in found.values())
