"""Android's clipboard: the plain text on it, for Paste.

Android calls the pasteboard the clipboard. Reading it is a call into the
platform through Chaquopy's ``java`` module, which only exists on Android.
Only text is read: a copied file arrives as a content URI that another app has
to grant access to, which is not supported yet.
"""

from __future__ import annotations


def read_text() -> str | None:
    """The text on the clipboard, or None if it holds none (or isn't readable).

    Android 12 and later show a "pasted from clipboard" notice when an app reads
    the clipboard. Only the first item is read, and only its text: a copied file
    or link comes back as None rather than as the URI's text.
    """
    from java import jclass  # type: ignore[import-not-found]  # Chaquopy

    activity = jclass("org.beeware.android.MainActivity").singletonThis
    manager = activity.getSystemService(
        jclass("android.content.Context").CLIPBOARD_SERVICE
    )
    if manager is None or not manager.hasPrimaryClip():
        return None
    clip = manager.getPrimaryClip()
    if clip is None or clip.getItemCount() < 1:
        return None
    text = clip.getItemAt(0).getText()
    return str(text) if text is not None and len(str(text)) > 0 else None
