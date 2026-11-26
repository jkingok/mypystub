"""Android's clipboard, through Chaquopy's ``java`` module (Android only).

Only text: a copied file arrives as a content URI that another app has to
grant access to, which isn't supported. ``java`` is imported inside each
function, so this module imports anywhere.
"""

from __future__ import annotations

from typing import Any


def _manager() -> Any:
    from java import jclass  # type: ignore[import-not-found]  # Chaquopy

    activity = jclass("org.beeware.android.MainActivity").singletonThis
    return activity.getSystemService(
        jclass("android.content.Context").CLIPBOARD_SERVICE
    )


def read_text() -> str | None:
    """The text on the clipboard, or None if it holds none (or isn't readable).

    Android 12 and later show a "pasted from clipboard" notice when an app reads
    the clipboard. Only the first item is read, and only its text: a copied file
    or link comes back as None rather than as the URI's text.
    """
    manager = _manager()
    if manager is None or not manager.hasPrimaryClip():
        return None
    clip = manager.getPrimaryClip()
    if clip is None or clip.getItemCount() < 1:
        return None
    text = clip.getItemAt(0).getText()
    return str(text) if text is not None and len(str(text)) > 0 else None


def write_text(text: str) -> bool:
    """Put `text` on the clipboard as plain text; False if there's no clipboard."""
    from java import jclass  # type: ignore[import-not-found]  # Chaquopy

    manager = _manager()
    if manager is None:
        return False
    clip = jclass("android.content.ClipData").newPlainText("text", text)
    manager.setPrimaryClip(clip)
    return True
