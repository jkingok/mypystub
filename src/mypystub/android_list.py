"""Android: a long press on a list row must not also select it.

Toga's Android ``DetailedList`` answers a long press by calling ``on_select``
and then showing the swipe actions (here Info and Setup) in a dialog. Our
``on_select`` runs the script, so a long press ran it too, while the dialog
that was meant to be the whole answer opened on top.

:func:`install` swaps Toga's long-press listener for one that shows the same
dialog without selecting the row. The actions don't need the selection: they are
given the row. It reaches into ``toga_android``, so it does nothing, and says so
in the log, if that module no longer looks the way it expects; Toga's own
behaviour then applies. It only works on Android, where that module exists.
"""

from __future__ import annotations

from typing import Any

_installed = False


def long_click(module: Any) -> Any:
    """Toga's ``onLongClick`` without its ``on_select()`` call.

    `module` is ``toga_android.widgets.detailedlist``; the names used here are
    its own, so the dialog is exactly the one Toga builds.
    """

    def on_long_click(self: Any, _view: Any) -> bool:
        with module.suppress_reference_error():
            actions = [
                action
                for action in [
                    module.Action(
                        self.interface._primary_action,
                        self.interface.on_primary_action,
                        self.impl._primary_action_enabled,
                    ),
                    module.Action(
                        self.interface._secondary_action,
                        self.interface.on_secondary_action,
                        self.impl._secondary_action_enabled,
                    ),
                ]
                if action.enabled
            ]
            if actions:
                row = self.interface.data[self.row_number]
                module.AlertDialog.Builder(self.impl._native_activity).setItems(
                    [action.name for action in actions],
                    module.DetailedListActionListener(actions, row),
                ).show()
        return True

    return on_long_click


def install() -> bool:
    """Use the replacement listener; False if Toga isn't as expected here.

    Safe to call again: it only does anything the first time.
    """
    global _installed
    if _installed:
        return True
    try:
        from toga_android.widgets import detailedlist  # pyright: ignore

        for name in (
            "DetailedListOnLongClickListener",
            "DetailedListActionListener",
            "Action",
            "AlertDialog",
            "suppress_reference_error",
        ):
            getattr(detailedlist, name)
        detailedlist.DetailedListOnLongClickListener.onLongClick = long_click(
            detailedlist
        )
    except (ImportError, AttributeError) as error:
        print(f"Long press still selects the row: {error}")
        return False
    _installed = True
    return True
