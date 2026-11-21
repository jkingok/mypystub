"""Updates for packages installed from git, which PyPI can't answer for (#328).

toga-console and Toga itself are bundled from their git repositories, so PyPI
either has no release (toga-console) or compares a development build with the
last release (Toga). pip records where such a package came from in its
dist-info, as ``direct_url.json`` (PEP 610): the repository, the branch or tag
asked for, and the commit installed. This asks the repository's host for the
newest commit on that branch, one request per repository and branch, and
reports a package whose commit is behind, with a link to the comparison.

Hosts: GitHub, GitLab and Bitbucket (see :mod:`git_hosts`). A requirement
pinned to a commit can't move, so it is never reported.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from importlib import metadata
from typing import Any
from urllib.parse import quote, urlsplit

import httpx2
from packaging.utils import canonicalize_name

from .git_hosts import host_of
from .maintenance import MaintenanceError

FULL_SHA = re.compile(r"[0-9a-f]{40}", re.IGNORECASE)
# The commit as plain text, from GitHub's commits API
GITHUB_SHA = "application/vnd.github.sha"


@dataclass(frozen=True)
class GitSource:
    """Where a package installed from git came from (its ``direct_url.json``)."""

    name: str
    url: str
    commit: str
    ref: str | None = None
    subdirectory: str | None = None

    @property
    def host(self) -> str | None:
        """The supported host the repository is on, or None."""
        return host_of(urlsplit(self.url).netloc)

    @property
    def path(self) -> list[str]:
        """The repository's path on its host: ``[owner, repo]`` and so on."""
        segments = [s for s in urlsplit(self.url).path.split("/") if s]
        if segments:
            segments[-1] = segments[-1].removesuffix(".git")
        return segments

    @property
    def pinned(self) -> bool:
        """Asked for by commit, so it can't move."""
        return self.ref is not None and FULL_SHA.fullmatch(self.ref) is not None

    @property
    def branch(self) -> str:
        """The branch or tag followed, for people: the default branch if none."""
        return self.ref or "the default branch"


@dataclass(frozen=True)
class GitUpdate:
    """A package from git whose branch has newer commits than the one installed."""

    name: str
    installed: str
    latest: str
    branch: str
    compare_url: str | None
    critical: bool = False

    def line(self) -> str:
        """One line for the Setup view."""
        note = " (app-critical)" if self.critical else ""
        return (
            f"{self.name}: newer commits on {self.branch} "
            f"({self.installed[:7]} → {self.latest[:7]}){note}"
        )


def source_from(name: str, direct_url: str | None) -> GitSource | None:
    """The git source in a ``direct_url.json`` text, or None if it isn't one."""
    if not direct_url:
        return None
    try:
        data = json.loads(direct_url)
    except ValueError:
        return None
    vcs = data.get("vcs_info") if isinstance(data, dict) else None
    if not isinstance(vcs, dict) or vcs.get("vcs") != "git" or not vcs.get("commit_id"):
        return None
    url = str(data.get("url", "")).removeprefix("git+")
    return GitSource(
        canonicalize_name(name),
        url,
        str(vcs["commit_id"]),
        vcs.get("requested_revision") or None,
        data.get("subdirectory") or None,
    )


def git_sources(paths: Iterable[str] | None = None) -> dict[str, GitSource]:
    """Packages installed from git on `paths` (default sys.path), by name."""
    found: dict[str, GitSource] = {}
    found_dists = (
        metadata.distributions(path=list(paths))
        if paths is not None
        else metadata.distributions()
    )
    for dist in found_dists:
        name = dist.metadata["Name"] if dist.metadata else None
        if not name:
            continue
        source = source_from(name, dist.read_text("direct_url.json"))
        if source is not None:
            found.setdefault(source.name, source)
    return found


def bundled_from_git(inventory: Mapping[str, str]) -> dict[str, GitSource]:
    """The packages of `inventory` (bundled with the app) that came from git."""
    names = {canonicalize_name(name) for name in inventory}
    return {name: s for name, s in git_sources().items() if name in names}


def _get(client: httpx2.Client, url: str, **headers: str) -> httpx2.Response:
    try:
        response = client.get(url, headers=headers, follow_redirects=True)
        response.raise_for_status()
        return response
    except httpx2.HTTPError as exc:
        raise MaintenanceError(f"Couldn't ask {urlsplit(url).netloc}: {exc}") from exc


def _json(client: httpx2.Client, url: str) -> Any:
    try:
        return _get(client, url).json()
    except ValueError as exc:
        raise MaintenanceError(f"Unexpected answer from {url}") from exc


def latest_commit(client: httpx2.Client, source: GitSource) -> str | None:
    """The newest commit on the source's branch, or None for an unknown host."""
    path, ref = source.path, source.ref
    match source.host:
        case "github.com" if len(path) == 2:
            owner, repo = path
            url = f"https://api.github.com/repos/{owner}/{repo}/commits/{ref or 'HEAD'}"
            return _get(client, url, Accept=GITHUB_SHA).text.strip()
        case "gitlab.com" if len(path) >= 2:
            project = "https://gitlab.com/api/v4/projects/" + quote("/".join(path), "")
            branch = ref or _json(client, project)["default_branch"]
            return str(
                _json(client, f"{project}/repository/commits/{quote(branch, '')}")["id"]
            )
        case "bitbucket.org" if len(path) == 2:
            repository = "https://api.bitbucket.org/2.0/repositories/{}/{}".format(
                *path
            )
            branch = ref or _json(client, repository)["mainbranch"]["name"]
            return str(
                _json(client, f"{repository}/commit/{quote(branch, '')}")["hash"]
            )
    return None


def compare_url(source: GitSource, latest: str) -> str | None:
    """The host's page comparing the installed commit with `latest`."""
    path, old = "/".join(source.path), source.commit
    match source.host:
        case "github.com":
            return f"https://github.com/{path}/compare/{old}...{latest}"
        case "gitlab.com":
            return f"https://gitlab.com/{path}/-/compare/{old}...{latest}"
        case "bitbucket.org":
            return f"https://bitbucket.org/{path}/branches/compare/{latest}%0D{old}"
    return None


def find_git_updates(
    client: httpx2.Client,
    sources: Mapping[str, GitSource],
    critical: Iterable[str] = (),
    on_check: Callable[[str], None] | None = None,
) -> list[GitUpdate]:
    """Sources whose branch has moved on, sorted by name.

    Packages from the same repository and branch (Toga's) share one request.
    `on_check` is called with each package's name as it is checked.
    """
    critical_names = {canonicalize_name(n) for n in critical}
    asked: dict[tuple[str, str | None], str | None] = {}
    updates: list[GitUpdate] = []
    for name, source in sorted(sources.items()):
        if on_check is not None:
            on_check(name)
        if source.pinned:
            continue
        key = (source.url.lower().removesuffix(".git"), source.ref)
        if key not in asked:
            asked[key] = latest_commit(client, source)
        latest = asked[key]
        if latest and latest.lower() != source.commit.lower():
            updates.append(
                GitUpdate(
                    name,
                    source.commit,
                    latest,
                    source.branch,
                    compare_url(source, latest),
                    name in critical_names,
                )
            )
    return updates
