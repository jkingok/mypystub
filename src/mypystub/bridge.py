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

    # Photos: Toga doesn't load this framework, so it's loaded here
    photos = load_library("Photos")
    PHPhotoLibrary = ObjCClass("PHPhotoLibrary")
    PHAccessLevelAddOnly = 1  # PHAccessLevel.addOnly
