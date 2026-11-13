"""Which branch and commit a build came from, for the About page.

A device has no Git, so the facts are written at build time by
``scripts/build_info.py`` (Fastlane runs it before every build) into
``resources/build_info.json``, which Briefcase bundles. A run straight from a
source tree on a desktop asks Git instead. About shows them only for builds that
aren't from ``main``: a release is from main, and its version says the rest.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

INFO_FILE = Path(__file__).resolve().parent / "resources" / "build_info.json"
REPO = Path(__file__).resolve().parents[2]  # src/mypystub -> the repository
MAIN = "main"


@dataclass(frozen=True)
class BuildInfo:
    """The branch (``HEAD`` when detached) and ``git describe`` of a build."""

    branch: str
    describe: str


def _git(repo: Path, *args: str) -> str | None:
    import subprocess  # here, not at the top: iOS can't start processes

    try:
        done = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() or None


def from_git(repo: Path) -> BuildInfo | None:
    """Ask Git about `repo`; None where there is no Git or no repository."""
    if sys.platform in ("ios", "android") or not shutil.which("git"):
        return None
    if not (repo / ".git").exists():
        return None
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    describe = _git(repo, "describe", "--tags", "--always", "--dirty")
    if branch is None or describe is None:
        return None
    return BuildInfo(branch, describe)


def load(path: Path = INFO_FILE) -> BuildInfo | None:
    """The facts written at build time, or None if there are none (or bad)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return BuildInfo(str(data["branch"]), str(data["describe"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def write(info: BuildInfo, path: Path = INFO_FILE) -> None:
    """Record `info` for the build to bundle."""
    path.write_text(json.dumps(asdict(info), indent=2) + "\n", encoding="utf-8")


def current() -> BuildInfo | None:
    """This build's facts: from a source tree's Git, else the bundled file.

    Git first, so a desktop source run isn't misled by a file left by an older
    build; on a device there is no Git and the file is what was built.
    """
    return from_git(REPO) or load()


def rows(info: BuildInfo | None) -> list[tuple[str, str]]:
    """About rows for a build not from main; nothing for main, or if unknown."""
    if info is None or info.branch == MAIN:
        return []
    branch = "(detached)" if info.branch == "HEAD" else info.branch
    return [("Branch", branch), ("Commit", info.describe)]
