"""Remember update-check answers for a day, and when the last check was.

Check for updates asks PyPI about every package, python.org about Python and
the git hosts about packages from git. The answers change slowly, so each is
kept for the rest of the day it was given, for the version that was asked
about: a second check that day asks only about what's new or has changed
version since (after Update all, say). The last check's answers also let the
Packages page show its results, with when they were found, before anything is
asked again.

Kept in the cache folder: losing it only means asking again. Free of Toga
imports, so it is unit tested on desktop.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

CACHE_NAME = "update_checks.json"


class UpdateCache:
    """Answers by kind ("pypi", "git", "python") and key, each for one version."""

    def __init__(self, path: Path, today: date | None = None) -> None:
        """Read `path` if it is there; `today` decides what is still fresh."""
        self.path = path
        self.today = today or date.today()
        self.entries: dict[str, dict[str, dict[str, Any]]] = {}
        self.checked: datetime | None = None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.entries = {
                kind: dict(found)
                for kind, found in data.get("entries", {}).items()
                if isinstance(found, dict)
            }
            if data.get("checked"):
                self.checked = datetime.fromisoformat(data["checked"])
        except (OSError, ValueError, TypeError, AttributeError):
            pass  # missing or damaged: start again

    def _entry(self, kind: str, key: str, version: str) -> dict[str, Any] | None:
        entry = self.entries.get(kind, {}).get(key)
        if isinstance(entry, dict) and entry.get("version") == version:
            return entry
        return None

    def get(self, kind: str, key: str, version: str = "") -> Any | None:
        """Today's answer for `key` at `version`, or None if there isn't one."""
        entry = self._entry(kind, key, version)
        if entry is not None and entry.get("day") == self.today.isoformat():
            return entry.get("value")
        return None

    def last(self, kind: str, key: str, version: str = "") -> Any | None:
        """The last answer for `key` at `version`, however old, or None."""
        entry = self._entry(kind, key, version)
        return None if entry is None else entry.get("value")

    def put(self, kind: str, key: str, value: Any, version: str = "") -> None:
        """Remember today's answer for `key` at `version`."""
        self.entries.setdefault(kind, {})[key] = {
            "version": version,
            "day": self.today.isoformat(),
            "value": value,
        }

    def save(self, checked: datetime | None = None) -> None:
        """Write the answers, noting `checked` as when the last check was."""
        if checked is not None:
            self.checked = checked
        data = {
            "checked": self.checked.isoformat() if self.checked else None,
            "entries": self.entries,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, indent=1), encoding="utf-8")
        except OSError as error:
            log.warning(f"Couldn't save the update checks: {error}")
