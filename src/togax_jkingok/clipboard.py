"""The system clipboard (iOS calls it the pasteboard): read and write it.

``await read(into)`` returns what was copied: a :class:`File` (a copied file,
preferred) or :class:`Text`, or None when there's nothing usable.
:func:`write_text` puts text on it, and :func:`suggested_name` is the name the
copying app gave its item, when it gave one.

- **iOS:** text and files. A file copied in the Files app comes through an
  item provider, and may first have to download from iCloud, so it's copied
  into the folder `into` (replacing the last one); a copied file URL is
  opened in place.
- **Android:** text (Android 12 and later show a "pasted" notice).
- **macOS, Windows, and Linux with GTK:** text, and a file copied in Finder,
  Explorer or a file manager (read in place).
- **Elsewhere** (the web, a terminal UI, or a desktop backend that can't be
  reached): nothing to read (None), and writing returns False.

The platform code is in private modules (``_ios_clipboard``,
``_android_clipboard``, ``_cocoa_clipboard``, ``_winforms_clipboard``,
``_gtk_clipboard``), imported only on their platform.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

# How the Files app marks what it copied. These are bookmarks, listed before the
# real type, and reading one gets a small binary plist instead of the file.
FILES_APP_TYPES = "com.apple.DocumentManager.FINode."
BOOKMARK_TYPES = (FILES_APP_TYPES, "com.apple.uikit.useractivity")
FOLDER_TYPE = "public.folder"
FOLDER_MESSAGE = "A folder can't be pasted. Compress it in Files, and copy the zip."
# Seconds to wait for a copied file, which might have to download from iCloud
PASTE_TIMEOUT = 120.0


@dataclass(frozen=True)
class Text:
    """Copied text."""

    text: str


@dataclass(frozen=True)
class File:
    """A copied file, at `path` (in the folder given to :func:`read`, or in place)."""

    path: Path


async def read(into: Path) -> Text | File | None:
    """What the clipboard holds, or None if nothing usable.

    Raises ValueError for a copied folder (see FOLDER_MESSAGE), and OSError if
    a copied file can't be read. On a desktop whose clipboard can't be reached
    (its backend's libraries missing), it's None rather than an error.
    """
    if sys.platform == "ios":
        from . import _ios_clipboard

        return await _ios_clipboard.read(into)
    if sys.platform == "android":
        from . import _android_clipboard

        text = _android_clipboard.read_text()
        return Text(text) if text else None
    try:
        if sys.platform == "darwin":
            from . import _cocoa_clipboard

            return _cocoa_clipboard.read()
        if sys.platform == "win32":
            from . import _winforms_clipboard

            return _winforms_clipboard.read()
        if sys.platform.startswith(("linux", "freebsd", "openbsd")):
            from . import _gtk_clipboard

            return await _gtk_clipboard.read()
    except (ImportError, AttributeError, NameError, OSError):
        return None
    return None


def write_text(text: str) -> bool:
    """Put `text` on the clipboard; False where there's no clipboard to write."""
    if sys.platform == "ios":
        from . import _ios_clipboard

        return _ios_clipboard.write_text(text)
    if sys.platform == "android":
        from . import _android_clipboard

        return _android_clipboard.write_text(text)
    try:
        if sys.platform == "darwin":
            from . import _cocoa_clipboard

            return _cocoa_clipboard.write_text(text)
        if sys.platform == "win32":
            from . import _winforms_clipboard

            return _winforms_clipboard.write_text(text)
        if sys.platform.startswith(("linux", "freebsd", "openbsd")):
            from . import _gtk_clipboard

            return _gtk_clipboard.write_text(text)
    except (ImportError, AttributeError, NameError, OSError):
        return False
    return False


def suggested_name() -> str | None:
    """The name the copying app gave the clipboard's item (iOS only), if any.

    For example ``interest tracker.py`` for a script copied from another app.
    """
    if sys.platform != "ios":
        return None
    from . import _ios_clipboard

    return _ios_clipboard.suggested_name()


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
