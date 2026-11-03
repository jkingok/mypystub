"""Remember which version of the app a user last ran (#125).

The launcher opens on the Help tab for a user who has never run the app, and
(see #126) on "What's New" the first time they open a new version. The last
version run is kept in a small text file in the app's cache folder.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

RECORD = "last_version.txt"


class StartState(Enum):
    """How this run relates to the last one."""

    NEW = "new"  # nothing recorded: the user has never run the app
    UPDATED = "updated"  # a different version was run last
    SAME = "same"  # this version was run last, or there's nothing to compare


def start_state(cache_dir: Path, version: str | None) -> StartState:
    """Compare the running `version` with the one recorded in `cache_dir`.

    A missing or empty `version` can't be compared, so it counts as ``SAME``.
    A file that exists but can't be read as text counts as ``UPDATED``, not
    ``NEW``: the user has been here before.
    """
    if not version:
        return StartState.SAME
    path = Path(cache_dir) / RECORD
    if not path.exists():
        return StartState.NEW
    try:
        recorded = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return StartState.UPDATED
    return StartState.SAME if recorded == version else StartState.UPDATED


def record_version(cache_dir: Path, version: str | None) -> bool:
    """Record `version` as the one last run; False if it couldn't be written.

    Errors are never raised: with a cache that can't be written, the user
    would look new on every start, so callers treat False as "don't show
    the new-user view".
    """
    if not version:
        return False
    try:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        (Path(cache_dir) / RECORD).write_text(version + "\n", encoding="utf-8")
    except OSError:
        return False
    return True
