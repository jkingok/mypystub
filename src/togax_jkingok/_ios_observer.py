"""The invisible UIKit view SafeArea watches its layout with (iOS only).

toga_iOS doesn't provide one, so it is defined here, once: defining an
Objective-C class a second time fails, so nothing else may define a class of
this name. On other platforms the module imports, and defines nothing.
"""

import sys

if sys.platform == "ios":
    from rubicon.objc import (  # pyright: ignore[reportMissingImports]
        objc_method,
        objc_property,
        send_super,
    )
    from toga_iOS.libs import UIView

    class SafeAreaObserverView(UIView):  # type: ignore[misc, valid-type]
        """An invisible view that tells its owner when its layout or safe area changes.

        SafeArea lays two over its own view, one ending at the top of the
        keyboard and one filling the box, and is told each time UIKit lays
        them out again (keyboard, size, rotation, bars).
        """

        owner = objc_property(object, weak=True)

        @objc_method
        def layoutSubviews(self) -> None:
            send_super(__class__, self, "layoutSubviews")
            if self.owner is not None:
                self.owner.native_changed()

        @objc_method
        def safeAreaInsetsDidChange(self) -> None:
            send_super(__class__, self, "safeAreaInsetsDidChange")
            if self.owner is not None:
                self.owner.native_changed()

        @objc_method
        def didMoveToWindow(self) -> None:
            # A tab that wasn't on screen at launch can join the window with
            # its size and safe area already set, so UIKit wouldn't lay the
            # observer out and its owner would never hear; ask for a layout
            send_super(__class__, self, "didMoveToWindow")
            if self.window is not None:
                self.setNeedsLayout()
