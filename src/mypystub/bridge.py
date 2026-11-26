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
from pathlib import Path
from typing import Any

from togax_jkingok import clipboard

# UIKit constants, plain numbers that are the same wherever this is imported
# A form sheet is a full-width sheet from the bottom on iPhone and a centred card
# on iPad. Left to itself, iOS 26 shows the share sheet as a small corner panel.

if sys.platform == "ios":
    from rubicon.objc import (  # pyright: ignore[reportMissingImports]
        ObjCClass,
        objc_const,
    )
    from rubicon.objc.runtime import (  # pyright: ignore[reportMissingImports]
        load_library,
    )
    from toga_iOS.libs import UIApplication, uikit

    def app_settings_url() -> str:
        """UIApplicationOpenSettingsURLString: opens this app's Settings page."""
        return str(objc_const(uikit, "UIApplicationOpenSettingsURLString"))

    def shared_application() -> Any:
        """UIApplication.sharedApplication, whether or not it's declared a property."""
        shared = UIApplication.sharedApplication
        return shared() if callable(shared) else shared

    # Photos: Toga doesn't load this framework, so it's loaded here
    photos = load_library("Photos")
    PHPhotoLibrary = ObjCClass("PHPhotoLibrary")
    PHAccessLevelAddOnly = 1  # PHAccessLevel.addOnly


async def read_pasteboard(into: Path) -> tuple[str, str] | None:
    """What the clipboard holds, as ``("file", path)`` or ``("text", string)``.

    None if nothing useful. See togax_jkingok.clipboard, which does the work:
    a copied folder raises ValueError, an unreadable file OSError.
    """
    content = await clipboard.read(into)
    if isinstance(content, clipboard.File):
        return ("file", str(content.path))
    if isinstance(content, clipboard.Text):
        return ("text", content.text)
    return None


def suggested_name() -> str | None:
    """The name the copying app gave the clipboard's item, if any (iOS only)."""
    return clipboard.suggested_name()
