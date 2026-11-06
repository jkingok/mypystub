"""Bring pasted scripts, files and archives into the user's folder (#36).

Reading the pasteboard is iOS-only (see ``bridge.py``). Everything after that
is here: naming, never overwriting without being told to, and unpacking
archives into a single folder.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import re
import shutil
import tarfile
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

# Unpacked on request. A .pyz is a program that runs as it is, so it isn't here.
ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz")

# Entries archives made on a Mac carry that are never the user's content
JUNK_NAMES = frozenset({"__MACOSX", ".DS_Store"})

# How the Files app marks what it copied. These are bookmarks, listed before the
# real type, and reading one gets a small binary plist instead of the file.
FILES_APP_TYPES = "com.apple.DocumentManager.FINode."
BOOKMARK_TYPES = (FILES_APP_TYPES, "com.apple.uikit.useractivity")
FOLDER_TYPE = "public.folder"
FOLDER_MESSAGE = "A folder can't be pasted. Compress it in Files, and copy the zip."


def is_folder(types: list[str]) -> bool:
    """Whether a pasteboard item with these type identifiers is a folder."""
    return FOLDER_TYPE in types


def file_type(types: list[str], has_text: bool) -> str | None:
    """The type identifier to read a pasteboard item's file from, or None.

    Anything from the Files app is a file, even when it also counts as text (a
    ``.py`` does), so that it keeps its name. Otherwise text stays text, and
    what's left, such as a copied image, is read as a file.
    """
    content = [uti for uti in types if not uti.startswith(BOOKMARK_TYPES)]
    from_files = any(uti.startswith(FILES_APP_TYPES) for uti in types)
    if not content or (has_text and not from_files):
        return None
    return content[0]


def keep_copy(source: Path, folder: Path) -> Path:
    """Copy `source` into `folder`, emptied first, keeping its name.

    For a file the system is about to delete. Only the latest paste is kept, so
    these don't pile up.
    """
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    return Path(shutil.copy2(source, folder / source.name))


# The same extension twice at the end of a name: ``test.py.py``, ``notes.txt.txt``.
# Letters only, so a name that ends in a version (``release 1.2.2``) is left alone.
REPEATED_EXTENSION = re.compile(r"(\.[A-Za-z][A-Za-z0-9]*)(?:\1)+$", re.IGNORECASE)


# Plain text isn't something to import: pasted text is taken to be Python, and a
# text file isn't accepted (see :func:`is_plain_text`)
TEXT_SUFFIXES = (".txt", ".text")
# Every ending that gives way to the single ``.py`` of a pasted script
SCRIPT_ENDINGS = re.compile(r"(?:\.(?:py|txt|text))+$", re.IGNORECASE)


def is_plain_text(name: str) -> bool:
    """Whether a file called `name` is plain text, which Paste doesn't accept."""
    return name.lower().endswith(TEXT_SUFFIXES)


def collapse_repeated_extension(name: str) -> str:
    """`name` with a repeated final extension reduced to one.

    ``test.py.py`` becomes ``test.py`` and ``notes.txt.txt`` becomes
    ``notes.txt``, whichever way the name arrived (typed, suggested by the app
    that copied the item, or the name of a copied file).
    """
    return REPEATED_EXTENSION.sub(r"\1", name)


def default_filename(now: datetime) -> str:
    """The suggested name for pasted text, such as ``pasted_20261103_0905``.

    Without the extension: pasted text is always saved as ``.py``, so the
    extension isn't the user's to type or change.
    """
    return f"pasted_{now:%Y%m%d_%H%M}"


def suggested_stem(suggested: str | None, now: datetime) -> str:
    """The name to offer for pasted text: the copied item's own, else the time.

    `suggested` is the name the other app gave the item, such as
    ``interest tracker.py``. Its extension is dropped: pasted text is always
    saved as ``.py``.
    """
    cleaned = clean_filename(suggested) if suggested else None
    if cleaned is None:
        return default_filename(now)
    return cleaned[: -len(".py")]


def clean_filename(typed: str) -> str | None:
    """A safe file name for pasted Python from what the user typed, or None.

    Folders are dropped (only the last part is kept), control characters are
    removed, and the name ends in one ``.py``. Pasted text is always Python, so
    ``test.py.py`` and ``notes.txt`` give ``test.py`` and ``notes.py``, while other
    extensions are part of the name. None means nothing usable was typed.
    """
    name = "".join(ch for ch in typed if ch >= " " and ch != "\x7f")
    name = PurePosixPath(name.replace("\\", "/")).name.strip()
    if name in ("", ".", ".."):
        return None
    name = collapse_repeated_extension(name)
    stem = SCRIPT_ENDINGS.sub("", name)
    if not stem.strip("."):
        return None
    return name if name[len(stem) :].lower() == ".py" else f"{stem}.py"


def _split_name(name: str) -> tuple[str, str]:
    """A file name as (stem, suffix), keeping ``.tar.gz`` together."""
    lowered = name.lower()
    for compound in (".tar.gz",):
        if lowered.endswith(compound):
            return name[: -len(compound)], name[-len(compound) :]
    path = Path(name)
    return path.stem, path.suffix


def unique_path(folder: Path, name: str) -> Path:
    """``folder / name``, or the first of ``name_2``, ``name_3``... that is free."""
    candidate = folder / name
    stem, suffix = _split_name(name)
    number = 2
    while candidate.exists():
        candidate = folder / f"{stem}_{number}{suffix}"
        number += 1
    return candidate


def would_overwrite(folder: Path, name: str) -> bool:
    """Whether a file or folder called `name` is already in `folder`."""
    return (folder / name).exists()


def is_archive(name: str) -> bool:
    """Whether `name` is an archive to offer to extract."""
    return name.lower().endswith(ARCHIVE_SUFFIXES)


def archive_top_level(archive: Path) -> list[str]:
    """The top-level names an archive would add, for a preview (junk removed)."""
    return sorted(_top_level(_members(archive)))


def _target(folder: Path, name: str, overwrite: bool) -> Path:
    return folder / name if overwrite else unique_path(folder, name)


def import_file(source: Path, folder: Path, overwrite: bool = False) -> Path:
    """Copy `source` into `folder` under its own name, as it is.

    A repeated final extension in the name (``x.txt.txt``) is reduced to one.

    An existing file is replaced only with ``overwrite``; otherwise the copy
    gets an incrementing name. Returns the path written.
    """
    target = _target(folder, collapse_repeated_extension(source.name), overwrite)
    shutil.copyfile(source, target)
    return target


def import_text(text: str, name: str, folder: Path, overwrite: bool = False) -> Path:
    """Write pasted `text` to `name` in `folder`; see :func:`import_file`."""
    target = _target(folder, name, overwrite)
    target.write_text(text, encoding="utf-8")
    return target


# -- Archives -------------------------------------------------------------------


def _members(archive: Path) -> list[str]:
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            return zf.namelist()
    with tarfile.open(archive) as tf:
        return tf.getnames()


def _safe(names: list[str]) -> None:
    """Refuse an archive with any path that leaves its folder."""
    for name in names:
        path = PurePosixPath(name.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"unsafe path in archive: {name}")


def _top_level(names: list[str]) -> set[str]:
    tops = set()
    for name in names:
        parts = PurePosixPath(name.replace("\\", "/")).parts
        if parts and parts[0] not in JUNK_NAMES:
            tops.add(parts[0])
    return tops


def _archive_stem(name: str) -> str:
    name = collapse_repeated_extension(name)
    return _split_name(name)[0] or name


def extract_archive(archive: Path, folder: Path) -> Path:
    """Unpack `archive` into one new folder in `folder`; return that folder.

    - If everything is inside a single top-level folder, that folder is used
      as it is (no folder around a folder).
    - Otherwise the contents go into a folder named after the archive.
    - The folder is never an existing one: a taken name gets ``_2``, ``_3``...
    - Mac junk (``__MACOSX``, ``.DS_Store``) is left out.
    - An archive with a path that would leave the folder is refused whole, and
      nothing is extracted.
    """
    names = _members(archive)
    _safe(names)
    tops = _top_level(names)
    with tempfile.TemporaryDirectory(dir=folder, prefix=".unpack_") as staging_name:
        staging = Path(staging_name)
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(staging)
        else:
            with tarfile.open(archive) as tf:
                tf.extractall(staging, filter="data")
        for junk in JUNK_NAMES:
            for found in list(staging.rglob(junk)):
                if found.is_dir():
                    shutil.rmtree(found, ignore_errors=True)
                else:
                    found.unlink(missing_ok=True)
        if len(tops) == 1 and (staging / next(iter(tops))).is_dir():
            content = staging / next(iter(tops))
            target = unique_path(folder, content.name)
        else:
            content = staging
            target = unique_path(folder, _archive_stem(archive.name))
        shutil.move(str(content), str(target))
    return target
