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

if sys.platform == "ios":
    from rubicon.objc import ObjCClass  # pyright: ignore[reportMissingImports]

    # UIKit: not declared in toga_iOS.libs.uikit
    UIActivityViewController = ObjCClass("UIActivityViewController")
