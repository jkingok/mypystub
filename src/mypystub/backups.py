"""Setup's Backup and Restore: the user's work and settings in one zip (#303).

A backup holds what can't be made again:

- ``documents/``: the Documents folder (scripts, projects, zipapps, web apps),
  without hidden files, ``__pycache__`` or the ``backups`` folders of earlier
  versions (#182);
- ``config/``: the app's settings (``launcher.toml``: Setup, aliases, run
  settings);
- ``manifest.json`` at the root, which marks it as a MyPyStub backup and says
  what's in it.

The cache (installed packages, built wheels, downloads, Native mode's venv) is
left out: it is all made again as needed. The zip is written file by file
straight to disk, never held in memory.

Restore takes only such a zip. Documents items are put back the way Paste puts
things back: what they replace is kept in ``backups/`` first. ``launcher.toml``
replaces the current one, which is kept the same way.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import paste_import, versions

MANIFEST = "manifest.json"
FORMAT = "mypystub-backup"
FORMAT_VERSION = 1
DOCUMENTS, CONFIG = "documents", "config"
CONFIG_FILES = ("launcher.toml",)  # what Restore puts back from config/
SKIPPED_NAMES = frozenset({"__pycache__", versions.BACKUPS})


class BackupProblem(ValueError):
    """Not a MyPyStub backup, or one this app can't read; the message says why."""


def _wanted(relative: Path) -> bool:
    return not any(
        part.startswith(".") or part in SKIPPED_NAMES for part in relative.parts
    )


def _files(root: Path) -> list[Path]:
    """`root`'s files to back up, relative to it, in a stable order."""
    if not root.is_dir():
        return []
    return sorted(
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file() and _wanted(path.relative_to(root))
    )


def create(
    documents: Path,
    config: Path,
    destination: Path,
    app_name: str,
    app_version: str,
    now: datetime | None = None,
) -> Path:
    """Write a backup zip into `destination`; return its path."""
    now = now or datetime.now().astimezone()
    destination.mkdir(parents=True, exist_ok=True)
    slug = app_name.lower().replace(" ", "_")
    archive = destination / f"{slug}-backup-{now.strftime('%Y%m%d-%H%M%S')}.zip"
    documents_files = _files(documents)
    config_files = [Path(name) for name in CONFIG_FILES if (config / name).is_file()]
    manifest = {
        "format": FORMAT,
        "version": FORMAT_VERSION,
        "app": app_name,
        "app_version": app_version,
        "created": now.isoformat(timespec="seconds"),
        "documents": sorted({p.parts[0] for p in documents_files}),
        "config": [p.as_posix() for p in config_files],
    }
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST, json.dumps(manifest, indent=2))
        for relative in documents_files:
            zf.write(documents / relative, f"{DOCUMENTS}/{relative.as_posix()}")
        for relative in config_files:
            zf.write(config / relative, f"{CONFIG}/{relative.as_posix()}")
    return archive


def read_manifest(archive: Path) -> dict:
    """The backup's manifest; BackupProblem if `archive` isn't a backup we read."""
    try:
        with zipfile.ZipFile(archive) as zf:
            try:
                manifest = json.loads(zf.read(MANIFEST))
            except KeyError:
                raise BackupProblem(
                    f"{archive.name} isn't a MyPyStub backup (it has no {MANIFEST})."
                ) from None
            names = zf.namelist()
    except zipfile.BadZipFile:
        raise BackupProblem(f"{archive.name} isn't a zip file.") from None
    except json.JSONDecodeError:
        raise BackupProblem(f"{archive.name}'s {MANIFEST} can't be read.") from None
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise BackupProblem(f"{archive.name} isn't a MyPyStub backup.")
    if manifest.get("version") != FORMAT_VERSION:
        raise BackupProblem(
            f"{archive.name} is a backup in a format this version of the app "
            f"doesn't read (version {manifest.get('version')})."
        )
    try:
        paste_import._safe(names)
    except ValueError as error:
        raise BackupProblem(str(error)) from None
    return manifest


@dataclass
class Restored:
    """What a restore did."""

    added: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)  # their old versions kept
    unchanged: list[str] = field(default_factory=list)
    config: list[str] = field(default_factory=list)


def restore(
    archive: Path,
    documents: Path,
    config: Path,
    *,
    settings: bool = True,
    now: datetime | None = None,
) -> Restored:
    """Put a backup back; what it replaces is kept in ``backups/`` first.

    With `settings` False, only Documents is restored.
    """
    read_manifest(archive)
    now = now or datetime.now()
    result = Restored()
    documents.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=documents, prefix=".restore_") as staging:
        root = Path(staging)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(root)
        saved = root / DOCUMENTS
        for item in sorted(saved.iterdir()) if saved.is_dir() else []:
            if item.is_dir():
                done = paste_import.place_folder(item, documents, now)
            else:
                done = paste_import.import_file(item, documents, now)
            if done.unchanged:
                result.unchanged.append(item.name)
            elif done.previous is not None:
                result.replaced.append(item.name)
            else:
                result.added.append(item.name)
        if settings:
            for name in CONFIG_FILES:
                source = root / CONFIG / name
                if not source.is_file():
                    continue
                target = config / name
                config.mkdir(parents=True, exist_ok=True)
                if target.is_file():
                    if versions.same_content(target, source):
                        continue
                    versions.back_up(target, now)
                shutil.copyfile(source, target)
                result.config.append(name)
    return result


def summary(manifest: dict) -> list[str]:
    """Lines saying what a backup holds, for the Restore preview."""
    made = (
        f"Made by {manifest.get('app', 'MyPyStub')} "
        f"{manifest.get('app_version', '')} on {manifest.get('created', '?')}."
    )
    lines = [made]
    items = manifest.get("documents") or []
    lines.append(f"Documents: {', '.join(items)}." if items else "Documents: nothing.")
    if manifest.get("config"):
        lines.append("Settings: Setup, aliases and each script's run settings.")
    return lines
