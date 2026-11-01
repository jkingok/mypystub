"""Cache, package-update and app-health logic for the Setup view (#77).

Kept free of Toga imports so it can be unit tested on desktop. Network calls take
an ``httpx2.Client``, so tests can serve fake responses and the UI can run them
off the event loop.

Sources (also linked from the Help page):
- Python releases: python.org's downloads API, ``PYTHON_RELEASES_URL``.
- Package versions: the PyPI JSON API, ``PYPI_JSON_URL``.
"""

import re
import shutil
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx2
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

PYTHON_RELEASES_URL = (
    "https://www.python.org/api/v2/downloads/release/?is_published=true"
)
PYPI_JSON_URL = "https://pypi.org/pypi/{name}/json"

# Bundled packages whose updates matter most (UI and TLS)
APP_CRITICAL = frozenset(
    {"toga-core", "toga-ios", "travertino", "rubicon-objc", "httpx2", "certifi"}
)

RELEASE_NAME = re.compile(r"Python (\d+\.\d+\.\d+\S*)")


class MaintenanceError(Exception):
    """A check couldn't complete, usually because the network is unavailable."""


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def dir_size(path: Path) -> int:
    """Total size in bytes of the files under `path` (0 if it doesn't exist)."""
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def human_size(size: int) -> str:
    """Format a byte count, for example "1.5 KB" or "3.0 MB"."""
    if size < 1024:
        return f"{size} B"
    value = float(size)
    for unit in ("KB", "MB", "GB"):
        value /= 1024
        if value < 1024 or unit == "GB":
            break
    return f"{value:.1f} {unit}"


def wipe(path: Path) -> None:
    """Delete `path` and everything in it, if it exists."""
    shutil.rmtree(path, ignore_errors=True)


# ---------------------------------------------------------------------------
# Python releases
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PythonStatus:
    """How the running Python compares with python.org's releases.

    :param current: The running version.
    :param latest_patch: The newest final release on the same branch (3.15.x).
    :param newer_stable: The newest final release on a newer branch (3.16.x), or
        None if the running branch is the newest released one.
    :param upcoming: The newest pre-release on a branch newer than any final
        release (3.16.0a1), or None if nothing is in pre-release.
    """

    current: Version
    latest_patch: Version | None
    newer_stable: Version | None
    upcoming: Version | None

    @property
    def patch_behind(self) -> bool:
        """Whether a newer release exists on the running branch."""
        return self.latest_patch is not None and self.latest_patch > self.current


def release_version(name: str) -> Version | None:
    """The version in a python.org release name such as "Python 3.15.2"."""
    match = RELEASE_NAME.fullmatch(name.strip())
    if not match:
        return None
    try:
        return Version(match.group(1))
    except InvalidVersion:
        return None


def python_status(releases: Iterable[Mapping[str, Any]], current: str) -> PythonStatus:
    """Compare `current` with python.org's list of published releases."""
    running = Version(current)
    branch = running.release[:2]
    versions = [v for r in releases if (v := release_version(str(r.get("name", ""))))]
    finals = [v for v in versions if not v.is_prerelease]
    same_branch = [v for v in finals if v.release[:2] == branch]
    newer_stable = max((v for v in finals if v.release[:2] > branch), default=None)
    newest_final_branch = max((v.release[:2] for v in finals), default=branch)
    upcoming = max(
        (
            v
            for v in versions
            if v.is_prerelease and v.release[:2] > max(newest_final_branch, branch)
        ),
        default=None,
    )
    return PythonStatus(
        current=running,
        latest_patch=max(same_branch, default=None),
        newer_stable=newer_stable,
        upcoming=upcoming,
    )


def fetch_json(client: httpx2.Client, url: str, source: str) -> Any:
    """GET `url` as JSON, turning any failure into a MaintenanceError."""
    try:
        response = client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.json()
    except (httpx2.HTTPError, ValueError) as exc:
        raise MaintenanceError(f"Couldn't reach {source}: {exc}") from exc


def check_python(client: httpx2.Client, current: str) -> PythonStatus:
    """Fetch python.org's releases and compare them with `current`."""
    return python_status(fetch_json(client, PYTHON_RELEASES_URL, "python.org"), current)


# ---------------------------------------------------------------------------
# Package versions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Update:
    """A package with a newer version on PyPI."""

    name: str
    installed: Version
    latest: Version
    critical: bool


def latest_on_pypi(client: httpx2.Client, name: str) -> Version | None:
    """The latest version PyPI lists for `name`, or None if it isn't on PyPI."""
    url = PYPI_JSON_URL.format(name=name)
    try:
        response = client.get(url, follow_redirects=True)
    except httpx2.HTTPError as exc:
        raise MaintenanceError(f"Couldn't reach PyPI: {exc}") from exc
    if response.status_code == 404:
        return None
    try:
        response.raise_for_status()
        return Version(response.json()["info"]["version"])
    except (httpx2.HTTPError, ValueError, KeyError, InvalidVersion) as exc:
        raise MaintenanceError(f"Unexpected answer from PyPI for {name}") from exc


def find_updates(
    client: httpx2.Client,
    inventory: Mapping[str, str],
    critical: Iterable[str] = (),
) -> list[Update]:
    """Packages in `inventory` (name -> version) with a newer version on PyPI."""
    critical_names = {canonicalize_name(n) for n in critical}
    updates: list[Update] = []
    for name, version in sorted(inventory.items()):
        latest = latest_on_pypi(client, name)
        try:
            installed = Version(version)
        except InvalidVersion:
            continue
        if latest is not None and latest > installed:
            canonical = canonicalize_name(name)
            updates.append(
                Update(canonical, installed, latest, canonical in critical_names)
            )
    return updates


def upgrade_requirements(updates: Iterable[Update]) -> list[str]:
    """Requirements that install exactly the versions found by find_updates."""
    return [f"{u.name}=={u.latest}" for u in updates]


# ---------------------------------------------------------------------------
# App health
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Health:
    """Things that only a new app build (TestFlight) can update."""

    python: PythonStatus
    bundled_updates: list[Update] = field(default_factory=list)

    @property
    def count(self) -> int:
        """How many updates need a new app build."""
        python = int(self.python.patch_behind) + int(bool(self.python.newer_stable))
        return python + len(self.bundled_updates)

    @property
    def summary(self) -> str:
        """One line for the Setup view."""
        if not self.count:
            return "✓ Up to date"
        noun = "update needs" if self.count == 1 else "updates need"
        return f"⚠ {self.count} {noun} a new app build (TestFlight)"

    def details(self) -> list[str]:
        """One line per finding, most important first."""
        lines: list[str] = []
        python = self.python
        if python.patch_behind:
            lines.append(f"Python {python.current} → {python.latest_patch} available")
        if python.newer_stable is not None:
            lines.append(f"Python {python.newer_stable} is out")
        if python.upcoming is not None:
            lines.append(f"Python {python.upcoming} is in pre-release")
        for update in sorted(self.bundled_updates, key=lambda u: not u.critical):
            note = " (app-critical)" if update.critical else ""
            lines.append(f"{update.name} {update.installed} → {update.latest}{note}")
        return lines
