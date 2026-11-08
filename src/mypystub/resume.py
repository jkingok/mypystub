"""Remember where the user was, to give the impression of resuming (#188).

iOS ends apps in the background whenever it likes, and the app is not told. So
the state is saved *as things change*, not on exit, in a small file in the
app's config folder, and read back at launch. It is only the surface: which tab,
which folder, which Setup or Help page, and whether a script was running. Values
and files are already saved as work goes, so those restore themselves.

The file belongs to one version of the app. A different version (the app may
behave differently) ignores it, and so does a file that is missing, unreadable
or of another schema. Nothing here raises for a bad file.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path, PurePosixPath

SCHEMA = 1
FILE_NAME = "resume.json"


@dataclass(frozen=True)
class Resume:
    """Where the user was. Folders are relative to their category's folder."""

    version: str
    tab: str = "List"
    category: str | None = None
    folder: str = ""  # the folder being browsed, "" for the category's top
    package: str = ""  # the package folder opened in the list, "" for none
    setup_page: str | None = None  # a Setup page open over the tabs
    help_page: str | None = None  # "Help", "What's New" or "About"
    running: str | None = None  # the settings key of a script that was running
    running_title: str = ""

    def to_json(self) -> str:
        """The state as the text saved to disk."""
        return json.dumps({"schema": SCHEMA, **asdict(self)}, indent=1)


def state_path(folder: Path) -> Path:
    """Where the state is kept in `folder` (the app's config folder)."""
    return Path(folder) / FILE_NAME


def load(path: Path, version: str) -> Resume | None:
    """The saved state, or None if there is none that applies to this version.

    None for a missing or unreadable file, another schema, another app version,
    or fields of the wrong type. `version` is the running app's.
    """
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        return None
    if not version or raw.get("version") != version:
        return None
    known = {f.name: f for f in fields(Resume)}
    values: dict[str, object] = {}
    for name, value in raw.items():
        field = known.get(name)
        if field is None:
            continue  # "schema", or something a later app added
        optional = "None" in str(field.type)
        if not isinstance(value, str) and not (optional and value is None):
            return None
        values[name] = value
    try:
        return Resume(**values)  # type: ignore[arg-type]
    except TypeError:
        return None


def save(path: Path, state: Resume) -> bool:
    """Save `state` atomically; False if it couldn't be written (never raises)."""
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(state.to_json(), encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        return False
    return True


def clear(path: Path) -> None:
    """Forget the saved state."""
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def nearest_existing(base: Path, relative: str) -> str:
    """The deepest folder of `relative` (inside `base`) that still exists.

    Walks up from the saved folder to its first parent that is still a folder,
    ending at "" (`base` itself). A path with `..` in it, an absolute one, or one
    that would leave `base` counts as gone.
    """
    root = Path(base).resolve()
    parts = [p for p in PurePosixPath(relative).parts if p not in ("", ".")]
    if ".." in parts or PurePosixPath(relative).is_absolute():
        return ""  # only ever a plain path down from the category's folder
    while parts:
        candidate = root.joinpath(*parts)
        try:
            inside = candidate.resolve().is_relative_to(root)
        except OSError:
            inside = False
        if inside and candidate.is_dir():
            return PurePosixPath(*parts).as_posix()
        parts.pop()
    return ""
