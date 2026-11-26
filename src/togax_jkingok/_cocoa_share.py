"""macOS's share menu (macOS with toga-cocoa only).

``NSSharingServicePicker`` isn't declared by toga_cocoa, so it's looked up
here, once. Imports anywhere; the lookup happens on first use.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

NS_MIN_Y_EDGE = 1  # NSRectEdge.minY: the menu opens below the anchor
# The picker on show: it must outlive the call, or the menu loses its owner
_showing: list[Any] = []


@cache
def _picker_class() -> Any:
    import toga_cocoa.libs  # noqa: F401  # pyright: ignore[reportMissingImports]
    from rubicon.objc import ObjCClass  # pyright: ignore[reportMissingImports]

    return ObjCClass("NSSharingServicePicker")


def share(path: Path, window: Any) -> bool:
    """Open the share menu for `path` at the bottom of `window` (an NSWindow)."""
    from rubicon.objc import NSMakeRect  # pyright: ignore[reportMissingImports]
    from toga_cocoa.libs import NSURL  # pyright: ignore[reportMissingImports]

    from .share import anchor_rect

    view = getattr(window, "contentView", None)
    if view is None:
        return False
    picker = _picker_class().alloc().initWithItems_([NSURL.fileURLWithPath_(str(path))])
    size = view.bounds.size
    # Cocoa's origin is at the bottom: the bottom centre is y = 1
    x, _, w, h = anchor_rect(size.width, size.height)
    picker.showRelativeToRect_ofView_preferredEdge_(
        NSMakeRect(x, 1.0, w, h), view, NS_MIN_Y_EDGE
    )
    _showing[:] = [picker]
    return True
