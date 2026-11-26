"""iOS's share sheet (iOS only).

``UIActivityViewController`` isn't declared by toga_iOS, so it's looked up
here, once. Imports anywhere; the lookup happens on first use.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any


@cache
def _controller_class() -> Any:
    from rubicon.objc import ObjCClass  # pyright: ignore[reportMissingImports]

    return ObjCClass("UIActivityViewController")


def share(path: Path, window: Any) -> bool:
    """Show the share sheet for `path` over `window` (a UIWindow)."""
    from rubicon.objc import NSMakeRect  # pyright: ignore[reportMissingImports]
    from toga_iOS.libs import (  # pyright: ignore[reportMissingImports]
        NSURL,
        NSMutableArray,
    )

    from .share import present_as_form_sheet

    presenting = getattr(window, "rootViewController", None)
    if presenting is None:
        return False
    # A sheet already up (another share, an alert) presents this one on top
    while presenting.presentedViewController is not None:
        presenting = presenting.presentedViewController
    items = NSMutableArray.alloc().init()
    items.addObject_(NSURL.fileURLWithPath_(str(path.resolve())))
    sheet = (
        _controller_class()
        .alloc()
        .initWithActivityItems(items, applicationActivities=None)
    )
    present_as_form_sheet(sheet, presenting.view, NSMakeRect)
    presenting.presentViewController(sheet, animated=True, completion=None)
    return True
