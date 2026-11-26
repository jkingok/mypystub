"""macOS's pasteboard (macOS only; see clipboard).

toga_cocoa doesn't declare ``NSPasteboard``, so it's looked up here, once. On
other platforms the module imports and defines nothing usable.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from . import clipboard

TEXT_TYPE = "public.utf8-plain-text"
FILE_TYPE = "public.file-url"

if sys.platform == "darwin":
    from rubicon.objc import ObjCClass  # pyright: ignore[reportMissingImports]
    from toga_cocoa import libs  # noqa: F401  # pyright: ignore[reportMissingImports]  (loads AppKit)

    NSPasteboard: Any = ObjCClass("NSPasteboard")
else:
    NSPasteboard: Any = None  # macOS only


def read() -> clipboard.Text | clipboard.File | None:
    """A copied file (Finder's), or text; None if neither."""
    pasteboard = NSPasteboard.generalPasteboard
    url = pasteboard.stringForType(FILE_TYPE)
    if url is not None and str(url).startswith("file:"):
        return clipboard.File(Path(unquote(urlparse(str(url)).path)))
    text = pasteboard.stringForType(TEXT_TYPE)
    return clipboard.Text(str(text)) if text is not None and str(text) else None


def write_text(text: str) -> bool:
    """Replace the pasteboard's contents with `text`."""
    pasteboard = NSPasteboard.generalPasteboard
    pasteboard.clearContents()
    return bool(pasteboard.setString(text, forType=TEXT_TYPE))
