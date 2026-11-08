"""The row of buttons above the list: New Folder and Paste.

Each adds something to the folder being browsed, so each is enabled only where
that works. A button is added to the row by listing it, with its rule, in
``list_action_buttons``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import toga

from . import folders
from .errors import guarded
from .ui_paste import PasteMixin


class ActionsMixin(PasteMixin):
    """Buttons that add to the folder the list is showing."""

    def __init__(self, host_app: toga.App, on_done: Callable[[Any], None]) -> None:
        super().__init__(host_app, on_done)
        self.new_folder_button = toga.Button(
            "New Folder", on_press=self.handle_new_folder
        )
        self.add_button_icon(self.new_folder_button, "folder.png")
        # Each button on the row, left to right, with the rule for when it works
        self.list_action_buttons: list[tuple[toga.Button, Callable[[], bool]]] = [
            (self.new_folder_button, self.can_add_here),
            (self.paste_button, self.can_add_here),
        ]

    def list_actions(self) -> toga.Box:
        """The row above the list: its buttons share the width equally."""
        for button, _ in self.list_action_buttons:
            button.style.flex = 1
            button.style.margin = (0, 4)
        row = toga.Row(children=[button for button, _ in self.list_action_buttons])
        self.update_list_actions()
        return row

    def can_add_here(self) -> bool:
        """Whether files and folders can be added to what the list shows.

        Only in Documents, or a folder in it. Not at the top (the categories),
        not in Examples (bundled, so read-only), and not inside a project or
        zipapp that has been opened to show its entry points.
        """
        return self.category == "Documents" and self.package_dir is None

    def update_list_actions(self) -> None:
        """Enable each button where its rule says it works, and grey the rest."""
        for button, available in self.list_action_buttons:
            button.enabled = available()

    @guarded
    def reload_menu(
        self, widget: toga.DetailedList | toga.Selection, **kwargs: Any
    ) -> None:
        """Rebuild the list, then fit the buttons to where it now is.

        Every change of place (opening a category, folder or package, going
        up, or a refresh) comes through here.
        """
        super().reload_menu(widget, **kwargs)
        self.update_list_actions()
        self.remember()

    @guarded
    async def handle_new_folder(
        self, widget: toga.Widget | None = None, **kwargs: Any
    ) -> None:
        """Ask for a name and make a folder in the folder being browsed."""
        if not self.can_add_here():
            await self.info(
                "Open Documents (or a folder in it) first: folders can't be "
                "added to the bundled examples, the top, or inside a project.",
                "New Folder",
            )
            return
        folder = self.get_current_dir()
        typed = ""
        while True:
            answer = await self.ask_text("New Folder", "Name for the new folder", typed)
            if answer is None:
                return
            typed = answer
            name = folders.clean_foldername(typed)
            if problem := folders.folder_name_problem(name):
                await self.info(problem, "New Folder")
                continue
            try:
                folders.make_folder(folder, name)
            except FileExistsError:
                await self.info(f"{name} already exists here.", "New Folder")
                continue
            except OSError as error:
                await self.error(f"Couldn't make the folder: {error}", "New Folder")
                return
            break
        self.reload_menu(self.script_list)
