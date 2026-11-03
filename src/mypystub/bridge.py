"""Objective-C classes the launcher needs that toga_iOS doesn't provide.

Import Objective-C classes from ``toga_iOS.libs`` whenever it has them: a second
``ObjCClass`` for the same class can clash with toga_iOS's copy ("multiple
implementation" errors), and toga_iOS also declares class properties on its
copies. Only classes, and frameworks, that toga_iOS doesn't set up belong here,
in this one place (enforced by tests/test_objc_usage.py).

Everything is defined on iOS only, so desktop and CI can import this module.
Re-check this list against toga_iOS.libs when Toga is upgraded: anything it
gains should be imported from there instead.
"""

import sys
from typing import Any

if sys.platform == "ios":
    from rubicon.objc import (  # pyright: ignore[reportMissingImports]
        ObjCClass,
        objc_const,
    )
    from rubicon.objc.runtime import (  # pyright: ignore[reportMissingImports]
        load_library,
    )
    from toga_iOS.libs import UIApplication, uikit

    # UIKit: not declared in toga_iOS.libs.uikit
    UIActivityViewController = ObjCClass("UIActivityViewController")

    def app_settings_url() -> str:
        """UIApplicationOpenSettingsURLString: opens this app's Settings page."""
        return str(objc_const(uikit, "UIApplicationOpenSettingsURLString"))

    def shared_application() -> Any:
        """UIApplication.sharedApplication, whether or not it's declared a property."""
        shared = UIApplication.sharedApplication
        return shared() if callable(shared) else shared

    # UIKit's pasteboard (the clipboard); toga_iOS doesn't declare it
    UIPasteboard = ObjCClass("UIPasteboard")

    # Photos: Toga doesn't load this framework, so it's loaded here
    photos = load_library("Photos")
    PHPhotoLibrary = ObjCClass("PHPhotoLibrary")
    PHAccessLevelAddOnly = 1  # PHAccessLevel.addOnly


def read_pasteboard() -> tuple[str, str] | None:
    """What the system pasteboard (clipboard) holds, or None if nothing useful.

    Returns ``("file", path)`` for a copied file, which is preferred, or
    ``("text", string)`` for copied text. Pasteboards only exist on iOS: on
    other platforms this returns None. A copied file lives outside the app, so
    its security-scoped access is started here and left open for the copy that
    follows; the system reclaims it when the app quits.
    """
    if sys.platform != "ios":
        return None
    pasteboard = UIPasteboard.generalPasteboard
    if pasteboard.hasURLs:
        url = pasteboard.URL
        if url is not None and url.isFileURL:
            url.startAccessingSecurityScopedResource()
            return ("file", str(url.path))
    if pasteboard.hasStrings:
        text = pasteboard.string
        if text is not None and str(text):
            return ("text", str(text))
    return None
