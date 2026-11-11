"""Is this the latest build? Ask GitHub's Releases before anything deeper (#203).

Each build is tagged with its version (``YYYY.M.D.N``, see ``about``) and has a
GitHub Release on the public repository. The newest Release says whether the
running build is current, and is much cheaper to ask than PyPI and python.org.
Only the version, never a token, is involved: the request is anonymous.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

import httpx2

from .maintenance import MaintenanceError, fetch_json

REPOSITORY = "jkingok/mypystub"
LATEST_URL = "https://api.github.com/repos/{repository}/releases/latest"
VERSION = re.compile(r"(\d{4})\.([1-9]\d?)\.([1-9]\d?)\.([1-9]\d*)")
NOTES_LIMIT = 600

Version = tuple[int, int, int, int]
Kind = Literal["current", "newer", "ahead", "not_release"]


def parse_version(text: str | None) -> Version | None:
    """A release build's version as numbers, or None for any other string.

    Numbers, not text: ``2026.11.10.1`` is later than ``2026.11.9.1``.
    """
    match = VERSION.fullmatch(text or "")
    if match is None:
        return None
    year, month, day, build = (int(part) for part in match.groups())
    return (year, month, day, build)


@dataclass(frozen=True)
class BuildStatus:
    """How the running build compares with the newest GitHub Release."""

    kind: Kind
    running: str
    latest: str = ""
    url: str = ""
    published: str = ""
    notes: str = ""

    @property
    def newer(self) -> bool:
        """Whether a later build than the running one has been released."""
        return self.kind == "newer"

    def lines(self) -> list[str]:
        """What to tell the user, most important first (empty when all is well)."""
        match self.kind:
            case "newer":
                when = f" ({self.published})" if self.published else ""
                return [
                    (
                        f"Build {self.latest}{when} is available in TestFlight; "
                        f"this is {self.running}."
                    )
                ]
            case "ahead":
                return [
                    (
                        f"This build, {self.running}, is newer than the latest "
                        f"release, {self.latest}: probably not released yet."
                    )
                ]
            case "not_release":
                return ["A development build isn't compared with GitHub Releases."]
            case _:
                return []


def latest_release(client: httpx2.Client, repository: str = REPOSITORY) -> dict:
    """The newest published Release of `repository`, as GitHub describes it.

    Raises MaintenanceError if GitHub can't be reached, has no Release yet, is
    rate-limiting, or answers with something unexpected.
    """
    data = fetch_json(client, LATEST_URL.format(repository=repository), "GitHub")
    if not isinstance(data, dict) or not isinstance(data.get("tag_name"), str):
        raise MaintenanceError("GitHub's answer about the latest release was odd.")
    return data


def compare(running: str, release: dict) -> BuildStatus:
    """Compare a release build's version with a GitHub Release.

    Raises MaintenanceError if the Release's tag isn't a build version.
    """
    tag = str(release["tag_name"])
    latest = parse_version(tag)
    current = parse_version(running)
    if latest is None or current is None:
        raise MaintenanceError(f"The latest release, {tag}, isn't a build version.")
    kind: Kind = (
        "current" if current == latest else "newer" if current < latest else "ahead"
    )
    notes = str(release.get("body") or "").strip()
    return BuildStatus(
        kind=kind,
        running=running,
        latest=tag,
        url=str(release.get("html_url") or ""),
        published=str(release.get("published_at") or "")[:10],
        notes=excerpt(notes),
    )


def excerpt(notes: str, limit: int = NOTES_LIMIT) -> str:
    """The start of a Release's notes, cut at a line end so the Markdown holds.

    Notes longer than `limit` end with an ellipsis line; the Release page,
    linked beside them, has the rest. A single line that long is cut where it
    reaches the limit.
    """
    if len(notes) <= limit:
        return notes
    cut = notes.rfind("\n", 0, limit)
    head = notes[:cut] if cut > 0 else notes[:limit]
    return head.rstrip() + "\n\n…"


def check_build(
    client: httpx2.Client, running: str | None, repository: str = REPOSITORY
) -> BuildStatus:
    """Is `running` the latest released build?

    A version that isn't a release build's (a development run) is not compared
    and costs no request. Otherwise one anonymous request to GitHub.
    """
    if parse_version(running) is None:
        return BuildStatus("not_release", running or "")
    return compare(str(running), latest_release(client, repository))
