"""The Info page for what an archive holds, shown before it is imported (#189).

Paste previews the thing being added as its Info page. For an archive that is
the Info of what it unpacks to: a project's Info, or a folder's README (or its
summary). The archive is unpacked into a scratch folder that is removed again,
unless it would unpack to more than :data:`PREVIEW_LIMIT` bytes, in which case
only its contents are listed.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import tarfile
import tempfile
import zipfile
from pathlib import Path

from . import info_pages, paste_import, row_info, scan

PREVIEW_LIMIT = 50 * 1024 * 1024  # bytes, once unpacked


def unpacked_size(archive: Path) -> int:
    """How many bytes `archive` holds, unpacked."""
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            return sum(info.file_size for info in zf.infolist())
    with tarfile.open(archive) as tf:
        return sum(member.size for member in tf.getmembers())


def project_title(folder: Path, fallback: str) -> str:
    """The title the list and Info will give the project once it's imported.

    That is its display name or ``[project] name``, as :func:`scan.scan_project`
    finds it, or `fallback` (the folder's name) if pyproject.toml can't be read.
    """
    try:
        return str(scan.scan_project(folder)["title"])
    except (OSError, ValueError):  # tomllib.TOMLDecodeError is a ValueError
        return fallback


def folder_info_html(folder: Path, title: str) -> str:
    """Info for an unpacked folder: a project's, else its README, else a summary."""
    if (folder / "pyproject.toml").is_file():
        return info_pages.project_info_html(folder, project_title(folder, title))
    if readme := row_info.find_readme(folder):
        text = readme.read_text(encoding="utf-8", errors="replace")
        return info_pages.readme_html(text, readme.name)
    message = row_info.no_readme_message("folder", title, scan.folder_summary(folder))
    return f"<h1>{info_pages.escape(title)}</h1>\n<p>{info_pages.escape(message)}</p>"


def archive_info_html(archive: Path, scratch: Path) -> str:
    """The Info page for `archive`, then its top-level contents.

    Raises OSError, tarfile.TarError, zipfile.BadZipFile or ValueError if the
    archive can't be read or has an unsafe path, so the caller can say so.
    """
    listing = paste_import.archive_top_level(archive)
    contents = info_pages.section(
        "Archive contents",
        info_pages.bullet_list(map(info_pages.escape, listing))
        if listing
        else "<p>(empty)</p>",
    )
    note = "<p>Import extracts these into a new folder here.</p>"
    title = paste_import.archive_stem(archive.name)
    if unpacked_size(archive) > PREVIEW_LIMIT:
        big = f"<h1>{info_pages.escape(title)}</h1>\n<p>It is too big to preview.</p>"
        return big + contents + note
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch, prefix="preview_") as folder:
        root = paste_import.extract_archive(archive, Path(folder))
        info = folder_info_html(root, root.name)
    return info + contents + note
