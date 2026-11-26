"""Share a file: the platform's share sheet, or the nearest thing on a desktop.

``share_file(path, window)`` hands one file to the user's choice of app:

- **iOS:** the share sheet (``UIActivityViewController``), as a form sheet,
  pointing at the bottom of the window if iOS shows it as a popover (iPad).
- **Android:** the chooser, with an ``ACTION_SEND`` intent. Another app can
  read the file only through a content URI, which only the app's own content
  provider can give: pass `android_uri`, a function that makes one for a path.
  Without one, a small text file is sent as its text, and anything else
  can't be shared (False).
- **macOS:** the share menu (``NSSharingServicePicker``), from the bottom of
  the window; if that can't be shown, Finder, with the file selected.
- **Windows:** Explorer, with the file selected. **Linux:** the file manager,
  on the file's folder.
- **Elsewhere** (the web, a terminal UI): False.

:func:`available` says whether sharing does anything here. The platform code is
in private modules (``_ios_share``, ``_android_share``, ``_cocoa_share``),
imported only on their platform.
"""

from __future__ import annotations

import sys
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any

# The largest text file Android shares as text when there's no content URI
ANDROID_TEXT_LIMIT = 500_000
# UIModalPresentationStyle.formSheet and UIPopoverArrowDirection.down
FORM_SHEET = 2
ARROW_DOWN = 2

DESKTOPS = ("darwin", "win32", "linux", "freebsd", "openbsd")


def available() -> bool:
    """Whether :func:`share_file` can show anything on this platform."""
    return sys.platform in ("ios", "android") or sys.platform.startswith(DESKTOPS)


def share_file(
    path: Path,
    window: Any = None,
    title: str = "Share",
    android_uri: Callable[[Path], Any] | None = None,
) -> bool:
    """Offer `path` to the user's choice of app; False if nothing could be shown.

    `window` (a Toga window) is where the sheet appears; the app's main window
    by default. `title` heads Android's chooser. `android_uri` makes a content
    URI for a path, on Android (see the module's description). Must run on the
    main thread, as a button's handler does. Raises FileNotFoundError if
    `path` isn't a file.
    """
    if not path.is_file():
        raise FileNotFoundError(f"{path} isn't there any more.")
    if sys.platform == "ios":
        from . import _ios_share

        return _ios_share.share(path, _native_window(window))
    if sys.platform == "android":
        from . import _android_share

        return _android_share.share(path, title, android_uri, ANDROID_TEXT_LIMIT)
    if sys.platform == "darwin":
        try:
            from . import _cocoa_share

            if _cocoa_share.share(path, _native_window(window)):
                return True
        except (ImportError, AttributeError, NameError, OSError):
            pass  # no Cocoa backend here: Finder still works
    return reveal(path)


def reveal(path: Path) -> bool:
    """Show `path` in the desktop's file manager; False where there isn't one.

    Finder and Explorer select the file; elsewhere its folder is opened.
    """
    if sys.platform in ("darwin", "win32"):
        import subprocess  # desktop only: iOS has no subprocess

        args = ["open", "-R", str(path)]
        if sys.platform == "win32":
            args = ["explorer", f"/select,{path}"]
        try:
            # Explorer's exit status means nothing, so only a launch failure counts
            done = subprocess.run(args, check=False)
        except OSError:
            return False
        return sys.platform == "win32" or done.returncode == 0
    if sys.platform.startswith(DESKTOPS):
        return bool(webbrowser.open(path.parent.as_uri()))
    return False


def anchor_rect(width: float, height: float) -> tuple[float, float, float, float]:
    """Where a sheet points: a zero-size spot at the bottom centre of a view.

    Never the whole view, which leaves a popover no room but a sliver at the side.
    """
    return (width / 2, max(height - 1, 0.0), 0.0, 0.0)


def present_as_form_sheet(
    controller: Any,
    view: Any,
    make_rect: Callable[[float, float, float, float], Any],
) -> None:
    """Show `controller` as a form sheet, anchored safely if iOS makes it a popover.

    rubicon reads ``popoverPresentationController`` as a method, because UIKit
    declares it in a category, so it has to be called. Setting attributes on it
    uncalled only touches a Python object, and an iPad then ends the app for
    want of a source view. `view` is the presenting controller's view, and
    `make_rect` builds a native rectangle from ``(x, y, width, height)``.
    """
    controller.modalPresentationStyle = FORM_SHEET
    popover = controller.popoverPresentationController()
    if popover is not None:
        size = view.bounds.size
        popover.sourceView = view
        popover.sourceRect = make_rect(*anchor_rect(size.width, size.height))
        popover.permittedArrowDirections = ARROW_DOWN


def _native_window(window: Any) -> Any:
    """The native window behind `window`, or the app's main window's; or None."""
    if window is None:
        import toga

        app = toga.App.app
        window = app.main_window if app is not None else None
    impl = getattr(window, "_impl", None)
    return getattr(impl, "native", None)
