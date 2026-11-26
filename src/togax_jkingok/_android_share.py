"""Android's share chooser, through Chaquopy's ``java`` module (Android only).

``java`` is imported inside :func:`share`, so this module imports anywhere.
"""

from __future__ import annotations

import mimetypes
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Types Android apps recognise better than the generic one
EXTRA_TYPES = {
    ".py": "text/x-python",
    ".pyz": "application/zip",
    ".log": "text/plain",
    ".md": "text/markdown",
}


def mime_type(path: Path) -> str:
    """The MIME type to announce for `path`."""
    known = EXTRA_TYPES.get(path.suffix.lower())
    return known or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def as_text(path: Path, limit: int) -> str | None:
    """`path`'s text, if it's a text file of at most `limit` bytes; else None."""
    if not mime_type(path).startswith("text/") or path.stat().st_size > limit:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def share(
    path: Path,
    title: str,
    make_uri: Callable[[Path], Any] | None,
    text_limit: int,
    jclass: Callable[[str], Any] | None = None,
) -> bool:
    """Start the chooser for `path`: by content URI, or as text; False if neither.

    `jclass` is Chaquopy's ``java.jclass`` (given only by tests, with stand-ins).
    """
    if jclass is None:
        from java import jclass as chaquopy_jclass  # type: ignore[import-not-found]

        jclass = chaquopy_jclass
    assert jclass is not None
    intent_class = jclass("android.content.Intent")
    send = intent_class(intent_class.ACTION_SEND)
    send.putExtra(intent_class.EXTRA_SUBJECT, path.name)
    uri = make_uri(path) if make_uri is not None else None
    if uri is not None:
        send.setType(mime_type(path))
        send.putExtra(intent_class.EXTRA_STREAM, uri)
        # The ClipData carries the grant through the chooser to the chosen app
        clip_data = jclass("android.content.ClipData")
        send.setClipData(clip_data.newRawUri(path.name, uri))
        send.addFlags(intent_class.FLAG_GRANT_READ_URI_PERMISSION)
    else:
        text = as_text(path, text_limit)
        if text is None:
            return False
        send.setType("text/plain")
        send.putExtra(intent_class.EXTRA_TEXT, text)
    chooser = intent_class.createChooser(send, title)
    chooser.addFlags(intent_class.FLAG_GRANT_READ_URI_PERMISSION)
    jclass("org.beeware.android.MainActivity").singletonThis.startActivity(chooser)
    return True
