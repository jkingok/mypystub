"""The GTK clipboard, for Linux and the BSDs (see clipboard).

Works with GTK 3 (``Gtk.Clipboard``) and GTK 4 (``Gdk.Clipboard``, read
asynchronously). ``gi`` is imported inside each function, so this module
imports anywhere; whichever GTK toga_gtk loaded is the one used.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from . import clipboard


def _gtk() -> tuple[Any, Any]:
    from gi.repository import Gdk, Gtk  # type: ignore[import-not-found]

    return Gtk, Gdk


def _file(uri: str) -> clipboard.File | None:
    if not uri.startswith("file:"):
        return None
    return clipboard.File(Path(unquote(urlparse(uri).path)))


async def read() -> clipboard.Text | clipboard.File | None:
    """A copied file (a ``file:`` URI), or text; None if neither."""
    gtk, gdk = _gtk()
    if gtk.get_major_version() < 4:
        board = gtk.Clipboard.get(gdk.SELECTION_CLIPBOARD)
        uris = board.wait_for_uris() or []
        if uris and (found := _file(str(uris[0]))):
            return found
        text = board.wait_for_text()
        return clipboard.Text(str(text)) if text else None
    board = gdk.Display.get_default().get_clipboard()
    loop = asyncio.get_running_loop()
    done: asyncio.Future[str | None] = loop.create_future()

    def finished(source: Any, result: Any) -> None:
        try:
            value = source.read_text_finish(result)
        except Exception:  # noqa: BLE001  (nothing readable as text)
            value = None
        if not done.done():
            done.set_result(value)

    board.read_text_async(None, finished)
    text = await done
    if not text:
        return None
    first = str(text).splitlines()[0] if str(text).strip() else ""
    return _file(first) or clipboard.Text(str(text))


def write_text(text: str) -> bool:
    """Replace the clipboard's contents with `text`."""
    gtk, gdk = _gtk()
    if gtk.get_major_version() < 4:
        board = gtk.Clipboard.get(gdk.SELECTION_CLIPBOARD)
        board.set_text(text, -1)
        board.store()
    else:
        gdk.Display.get_default().get_clipboard().set(text)
    return True
