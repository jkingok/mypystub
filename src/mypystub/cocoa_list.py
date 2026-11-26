"""macOS: right-clicking a list row must not also select it.

Toga's Cocoa ``DetailedList`` answers a right-click by selecting the row under
the pointer and then showing the swipe actions (here Info and Setup) as a menu.
Selecting calls ``on_select``, and ours runs the script or opens the folder, so
a right-click ran the row too. Worse, the menu items remember the row's number,
and once a folder has opened the list holds other rows: Setup or Info then
acted on whatever now has that number, so the categories' and ``..``'s own
Setup and Info couldn't be reached.

:func:`install` gives Toga a subclass of its table view whose context menu is
the same one, without the selection. That is how macOS lists usually behave:
the right-clicked row is outlined, not selected. It reaches into
``toga_cocoa``, so it does nothing, and says so in the log, if that module no
longer looks the way it expects; Toga's own behaviour then applies. It only
works on macOS, where that module exists. (On Android, see android_list.)
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

_installed = False


def menu_titles(impl: Any) -> list[tuple[str, str]]:
    """The enabled actions as (title, selector) pairs, in Toga's order."""
    items = []
    if impl.primary_action_enabled:
        items.append((impl.interface._primary_action, "primaryActionOnRow:"))
    if impl.secondary_action_enabled:
        items.append((impl.interface._secondary_action, "secondaryActionOnRow:"))
    return items


def make_list_class(module: Any) -> Any:
    """A subclass of Toga's ``TogaList`` whose context menu doesn't select.

    `module` is ``toga_cocoa.widgets.detailedlist``.
    """
    from rubicon.objc import SEL, objc_method  # pyright: ignore[reportMissingImports]

    class TogaListNoSelect(module.TogaList):  # type: ignore[misc, valid-type, name-defined]
        """Toga's list, with a context menu that leaves the selection alone."""

        # No annotations: rubicon reads them as Objective-C types (an object in,
        # an object out, as Toga's own method has)
        @objc_method
        def menuForEvent_(self, event):
            items = menu_titles(self.impl)
            point = self.convertPoint(event.locationInWindow, fromView=None)
            row = self.rowAtPoint(point)
            popup = None
            if items and row >= 0:
                popup = module.NSMenu.alloc().initWithTitle("popup")
                for title, selector in items:
                    item = popup.addItemWithTitle(
                        title, action=SEL(selector), keyEquivalent=""
                    )
                    item.tag = row
            self.impl._popup = popup  # as Toga keeps it
            return popup

    return TogaListNoSelect


def install() -> bool:
    """Use the replacement table view; False if Toga isn't as expected here.

    Call it before any ``DetailedList`` is made: lists made earlier keep Toga's
    own. Safe to call again: it only does anything the first time.
    """
    global _installed
    if _installed:
        return True
    try:
        from rubicon.objc import SEL  # pyright: ignore[reportMissingImports]
        from toga_cocoa.widgets import detailedlist  # pyright: ignore

        for name in ("TogaList", "NSMenu"):
            getattr(detailedlist, name)
        for selector in ("primaryActionOnRow:", "secondaryActionOnRow:"):
            if not detailedlist.TogaList.instancesRespondToSelector(SEL(selector)):
                raise AttributeError(f"TogaList has no {selector}")
        detailedlist.TogaList = make_list_class(detailedlist)
    except (ImportError, AttributeError) as error:
        log.warning(f"Right-click still selects the row: {error}")
        return False
    _installed = True
    return True
