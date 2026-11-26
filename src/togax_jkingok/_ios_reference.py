"""The safe area a window made the current way would have (iOS only).

Toga makes its window with ``initWithFrame:`` and attaches it to its scene
afterwards. On iOS 18.5 and 27.2 such a window keeps its portrait safe-area
insets after the device turns to landscape (top 62, bottom 34 instead of 62
at each side and 21 at the bottom), so content goes under the notch or the
Dynamic Island (#305). A window made with ``initWithWindowScene:``, as Apple's
templates make theirs, turns with the device. One such window per scene is
kept here, invisible, behind everything and ignoring touches, and only read.

Nothing here defines an Objective-C class. On other platforms the module
imports, and :func:`scene_insets` says nothing.
"""

from __future__ import annotations

import sys
from typing import Any

# The invisible window for each scene, by the scene's address
_windows: dict[int, Any] = {}


def scene_insets(window: Any) -> tuple[float, float, float, float] | None:
    """Top, right, bottom and left insets for `window`'s scene, or None.

    None off iOS, before the window has a scene, or if UIKit refuses.
    """
    if sys.platform != "ios" or window is None:
        return None
    try:
        scene = window.windowScene
        if scene is None:
            return None
        key = int(getattr(scene, "ptr", None).value or 0)
        reference = _windows.get(key)
        if reference is None:
            reference = _make(scene)
            _windows[key] = reference
        safe = reference.safeAreaInsets
        return (safe.top, safe.right, safe.bottom, safe.left)
    except Exception:  # noqa: BLE001  (a reading must never break layout)
        return None


def _make(scene: Any) -> Any:
    from toga_iOS.libs import (  # pyright: ignore[reportMissingImports]
        UIColor,
        UIViewController,
        UIWindow,
    )

    reference = UIWindow.alloc().initWithWindowScene(scene)
    reference.rootViewController = UIViewController.alloc().init()
    reference.backgroundColor = UIColor.clearColor
    reference.userInteractionEnabled = False
    reference.windowLevel = -1000.0  # behind the app's own window
    reference.alpha = 0.01  # a hidden window isn't laid out
    reference.hidden = False
    return reference
