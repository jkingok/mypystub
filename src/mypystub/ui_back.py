"""The system Back button: what it does on each screen (Android).

On Android the Back gesture or button reaches :meth:`BackMixin.handle_back`
through :mod:`android_back`. In the launcher it does what the screen's own
Back, Cancel or Done does, goes up a level in the list, or back to the tab shown
before. When there is nowhere further back, or a prototype is showing, it does
nothing of its own and Android does its usual thing.

=========================  =================================================
Showing                    Back
=========================  =================================================
A screen of ours           its own Back, Cancel or Done (``push_screen``)
A prototype's takeover     left to Android: the prototype doesn't know about
                           our Back, and its own may do more than pop (save,
                           confirm). A prototype that wants Back handles it
                           itself, with its own callback, which Android asks
                           before ours.
List: a package            the folder it is in
List: a folder             the folder above it
List: a category           the list of categories
Any tab, otherwise         the tab shown before it, in the order they were
                           shown
The first tab shown        left to Android: it leaves the app
=========================  =================================================

Kept to the launcher's own state, so it is tested on desktop.
"""

from __future__ import annotations

from typing import Any

import toga

from .ui_base import PrototypeBase


class BackMixin(PrototypeBase):
    """Routes the system Back button to the right action for what is showing."""

    TAB_HISTORY = 20  # tabs remembered for Back

    def note_tab(self, name: str) -> None:
        """Record that tab `name` is showing (a repeat isn't recorded twice)."""
        if self.tab_history and self.tab_history[-1] == name:
            return
        self.tab_history.append(name)
        del self.tab_history[: -self.TAB_HISTORY]

    def handle_back(self) -> bool:
        """Do what Back means here. False to leave it to Android."""
        mw = self.app.main_window
        assert isinstance(mw, toga.MainWindow)
        stack = self.content_stack()
        if self.tabs is not None and mw.content is self.tabs:
            return self.back_in_tabs()
        if self.screen_bases and len(stack) == self.screen_bases[-1] + 1:
            # One of our screens is on top: its own Back, Cancel or Done
            self.back_actions[-1]()
            return True
        # A prototype is showing: its Back is its own business
        return False

    def back_in_tabs(self) -> bool:
        """Back on the tabs: up the list first, then the tab shown before."""
        current: Any = self.tabs.current_tab
        name = str(current.text) if current is not None else ""
        self.note_tab(name)  # in case the switch hasn't been recorded yet
        if name == "List" and self.list_up():
            return True
        if len(self.tab_history) > 1:
            self.tab_history.pop()
            # Recorded again as it shows, but it is already the last entry
            self.tabs.current_tab = self.tab_history[-1]
            return True
        return False

    def list_up(self) -> bool:
        """Go up a level in the list. False at the list of categories."""
        if self.package_dir is not None:
            self.package_dir = None
        elif self.subfolder.parts:
            self.subfolder = self.subfolder.parent
        elif self.category is not None:
            self.show_category(None)
        else:
            return False
        self.reload_menu(self.script_list)
        self.remember()
        return True
