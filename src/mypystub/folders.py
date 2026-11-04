"""Making a new folder in the user's Documents.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from .scan import SKIPPED_FOLDERS


def clean_foldername(typed: str) -> str:
    """A folder name from what the user typed: no path, no control characters.

    Only the last part of a path is kept, so a folder can only be made in the
    folder being browsed. The result may be empty (see
    :func:`folder_name_problem`).
    """
    name = "".join(ch for ch in typed if ch >= " " and ch != "\x7f")
    return PurePosixPath(name.replace("\\", "/")).name.strip()


def folder_name_problem(name: str) -> str | None:
    """Why a folder can't be called `name`, or None if it can.

    The list leaves out folders that start with a dot, and a few the launcher
    uses for itself, so a folder with one of those names would vanish.
    """
    if name in ("", ".", ".."):
        return "Enter a name for the folder."
    if name.startswith("."):
        return "A name starting with a dot would be hidden from the list."
    if name in SKIPPED_FOLDERS:
        return f"{name} is a name the list leaves out. Choose another."
    return None


def make_folder(parent: Path, name: str) -> Path:
    """Make the folder ``parent / name``.

    Raises FileExistsError if a file or folder is already called that, so a
    folder is never replaced or merged into.
    """
    path = parent / name
    path.mkdir()
    return path
