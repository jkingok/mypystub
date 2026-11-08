"""What to send when the user shares a script, project or zipapp (#147).

The share sheet shares files. A script (``.py``) or zipapp (``.pyz``) is shared
as it is. A project is a folder, so it is zipped into a single top-level folder
holding its content, which is what Paste extracts: share it on one device, paste
it on another, and the project comes back as it was.

The user's saved Setup (arguments and variables, in ``launcher.toml``) is never
included: it belongs to the device and may hold values they would not want to
send. Caches, version control and build output are left out too.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

# Never part of what is shared, wherever they are in the project
SKIP_NAMES = frozenset(
    {"__pycache__", "build", "dist", "node_modules", "launcher.toml", ".DS_Store"}
)
SKIP_SUFFIXES = (".egg-info", ".pyc", ".pyo")
SHARE_FOLDER = "share"


def share_available() -> bool:
    """Whether sharing is offered: the share sheet is iOS only."""
    return sys.platform == "ios"


def skipped(relative: Path) -> bool:
    """Whether a path inside a project stays out of the zip."""
    for part in relative.parts:
        if part in SKIP_NAMES or part.endswith(SKIP_SUFFIXES):
            return True
        if part.startswith("."):  # hidden: .git, .venv, .env and the like
            return True
    return False


def zip_project(folder: Path, destination: Path) -> Path:
    """Zip `folder` into `destination` as ``<name>.zip``; return its path.

    Everything is under one top-level folder named for the project, so Paste
    uses it as it is.
    """
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / f"{folder.name}.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as zf:
        for item in sorted(folder.rglob("*")):
            relative = item.relative_to(folder)
            if item.is_file() and not skipped(relative):
                zf.write(item, Path(folder.name) / relative)
    return archive


def prepare_share(source: Path, cache_dir: Path) -> Path:
    """The file to hand to the share sheet for `source`.

    A file (script or zipapp) is shared as it is. A folder is zipped in the
    cache folder, after clearing what an earlier share left there.
    """
    if source.is_file():
        return source
    if not source.is_dir():
        raise FileNotFoundError(f"{source} isn't there any more.")
    scratch = cache_dir / SHARE_FOLDER
    shutil.rmtree(scratch, ignore_errors=True)
    return zip_project(source, scratch)
