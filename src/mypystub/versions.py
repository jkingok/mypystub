"""Backups of what a paste replaces (#182).

AI tools often iterate on code, and an iteration can break what worked. So
pasting over a script, zipapp or project that is already there no longer asks:
the newest paste keeps the **right name** (so saved settings, which are keyed
by path, still apply) and what it replaces is backed up first.

Backups are one kind of thing, a single file each, in a ``backups`` folder
beside the original. The folder shows in the Files app but not in the launcher's
list:

- a script or zipapp is copied, with the time before its last extension:
  ``backups/tool.2026-11-05T143207.py``, ``backups/app.2026-11-05T143207.pyz``;
- a project folder is zipped: ``backups/proj.2026-11-05T143207.zip``.

The time is when the backup was made, which is when the next version was
imported: a backup is "the version that was installed before then". Nothing is
done for settings; only the code or project is backed up and restored.

Pasting exactly what is already there (the same content hash, for folders too)
changes nothing. The launcher's Setup lists the backups, with Restore and
Delete.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

BACKUPS = "backups"  # beside the original; the launcher's list hides it
STAMP_FORMAT = "%Y-%m-%dT%H%M%S"
# <base>.<stamp>[.<last extension>]
BACKUP_NAME = re.compile(
    r"(?P<base>.+)\.(?P<stamp>\d{4}-\d{2}-\d{2}T\d{6})(?P<suffix>\.[A-Za-z0-9]+)?"
)


@dataclass(frozen=True)
class Backup:
    """A backup of something, kept in a ``backups`` folder."""

    path: Path
    when: datetime  # when it was backed up: the version before then
    size: int  # bytes of the backup file itself
    is_folder: bool  # a zipped project folder, not a single file


def backups_folder(item: Path) -> Path:
    """Where the backups of `item` are kept: beside it."""
    return item.parent / BACKUPS


def stamp(now: datetime) -> str:
    """The time put in a backup's name."""
    return now.strftime(STAMP_FORMAT)


def backup_name(item: Path, when: datetime) -> str:
    """The file name a backup of `item` has, in the backups folder."""
    if item.is_dir():
        return f"{item.name}.{stamp(when)}.zip"
    suffix = item.suffix
    base = item.name[: -len(suffix)] if suffix else item.name
    return f"{base}.{stamp(when)}{suffix}"


def content_hash(path: Path) -> str:
    """A hash of a file's bytes, or of a folder's file names and bytes."""
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.read_bytes())
        return digest.hexdigest()
    for file in sorted(f for f in path.rglob("*") if f.is_file()):
        digest.update(file.relative_to(path).as_posix().encode("utf-8") + b"\0")
        digest.update(file.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def same_content(first: Path, second: Path) -> bool:
    """Whether two files, or two folders, hold exactly the same content."""
    try:
        if first.is_dir() != second.is_dir():
            return False
        return content_hash(first) == content_hash(second)
    except OSError:
        return False


def back_up(item: Path, now: datetime) -> Path:
    """Copy a file, or zip a folder, into the backups folder; return the backup.

    `item` is left where it is, for the caller to replace.
    """
    folder = backups_folder(item)
    folder.mkdir(exist_ok=True)
    target = folder / backup_name(item, now)
    if item.is_dir():
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(f for f in item.rglob("*") if f.is_file()):
                archive.write(file, file.relative_to(item).as_posix())
    else:
        shutil.copy2(item, target)
    return target


def parse(name: str) -> tuple[str, str, datetime] | None:
    """(base, suffix, time) from a backup's file name, or None if it isn't one."""
    match = BACKUP_NAME.fullmatch(name)
    if match is None:
        return None
    try:
        when = datetime.strptime(match["stamp"], STAMP_FORMAT)
    except ValueError:
        return None
    return match["base"], match["suffix"] or "", when


def list_backups(item: Path) -> list[Backup]:
    """The backups of `item`, newest first."""
    found: list[Backup] = []
    folder = backups_folder(item)
    try:
        files = [f for f in folder.iterdir() if f.is_file()]
    except OSError:
        return found
    for file in files:
        parsed = parse(file.name)
        if parsed is None:
            continue
        base, suffix, when = parsed
        is_folder = suffix == ".zip" and base == item.name and not item.is_file()
        if base + suffix != item.name and not is_folder:
            continue
        try:
            found.append(Backup(file, when, file.stat().st_size, is_folder))
        except OSError:
            continue
    return sorted(found, key=lambda b: b.when, reverse=True)


def _safe_members(archive: zipfile.ZipFile) -> None:
    for name in archive.namelist():
        parts = name.replace("\\", "/").split("/")
        if name.startswith("/") or ".." in parts:
            raise ValueError(f"unsafe path in backup: {name}")


def restore(backup: Path, item: Path, now: datetime) -> Path | None:
    """Make `backup` the current `item`; return the backup of what it replaced.

    What is there now is backed up first, so restoring never loses anything.
    The restored backup is kept (Delete removes it).
    """
    if not backup.is_file() or parse(backup.name) is None:
        raise ValueError(f"{backup.name} isn't a backup.")
    previous = back_up(item, now) if item.exists() else None
    if backup.suffix == ".zip" and (item.is_dir() or not item.exists()):
        with zipfile.ZipFile(backup) as archive:
            _safe_members(archive)
            if item.is_dir():
                shutil.rmtree(item)
            item.mkdir()
            archive.extractall(item)
    else:
        shutil.copy2(backup, item)
    return previous


def delete(backup: Path) -> None:
    """Remove a backup."""
    if backup.parent.name != BACKUPS or parse(backup.name) is None:
        raise ValueError(f"{backup.name} isn't a backup.")
    backup.unlink()
