"""Windows' clipboard, through WinForms (Windows only; see clipboard).

``System.Windows.Forms`` (pythonnet, as toga_winforms uses) is imported inside
each function, so this module imports anywhere. The clipboard is read on the
app's main thread, which WinForms makes a single-threaded apartment.
"""

from __future__ import annotations

from pathlib import Path

from . import clipboard


def read() -> clipboard.Text | clipboard.File | None:
    """The first copied file (Explorer's), or text; None if neither."""
    from System.Windows.Forms import (  # type: ignore[import-not-found]
        Clipboard,
    )

    if Clipboard.ContainsFileDropList():
        files = list(Clipboard.GetFileDropList())
        if files:
            return clipboard.File(Path(str(files[0])))
    if Clipboard.ContainsText():
        text = str(Clipboard.GetText())
        return clipboard.Text(text) if text else None
    return None


def write_text(text: str) -> bool:
    """Replace the clipboard's contents with `text`."""
    from System.Windows.Forms import (  # type: ignore[import-not-found]
        Clipboard,
    )

    Clipboard.SetText(text)
    return True
