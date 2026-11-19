"""The row of buttons above the list: New, New Folder and Paste.

Each adds something to the folder being browsed, so each is enabled only where
that works. A button is added to the row by listing it, with its rule, in
``list_action_buttons``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import toga

from . import folders, new_items
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
        # A new script or project, from the templates (#146)
        self.new_button = toga.Button("New", on_press=self.handle_new)
        # An icon like its neighbours', so the three line up (the list's script icon)
        self.add_button_icon(self.new_button, "file-code.png")
        self.new_name: toga.TextInput | None = None
        # The details screen's fields, by name: description, bundle, author
        self.new_details: dict[str, toga.TextInput] = {}
        # Each button on the row, left to right, with the rule for when it works
        self.list_action_buttons: list[tuple[toga.Button, Callable[[], bool]]] = [
            (self.new_button, self.can_add_here),
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

    @guarded
    async def handle_new(
        self, widget: toga.Widget | None = None, **kwargs: Any
    ) -> None:
        """Start a new script or project in the folder being browsed (#146)."""
        if not self.can_add_here():
            await self.info(
                "Open Documents (or a folder in it) first: new scripts and "
                "projects can't go in the bundled examples, the top, or inside "
                "a project.",
                "New",
            )
            return
        self.new_name = toga.TextInput(placeholder="Name, such as My Tool", flex=1)
        self.push_screen(
            "New",
            toga.Column(
                margin=8,
                children=[
                    toga.Row(
                        children=[toga.Button("Cancel", on_press=self.cancel_new)]
                    ),
                    toga.Label("Name"),
                    toga.Box(children=[self.new_name]),
                    toga.Label(
                        "A script is one file, the quickest start.\n"
                        "A project is a Briefcase app: it also builds\n"
                        "on a computer for iOS, Android and desktop."
                    ),
                    toga.Row(
                        children=[
                            toga.Button(
                                "Script", on_press=self.create_new_script, flex=1
                            ),
                            toga.Button(
                                "Project", on_press=self.create_new_project, flex=1
                            ),
                        ]
                    ),
                ],
            ),
        )

    @guarded
    def cancel_new(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Back, creating nothing."""
        self.new_name = None
        self.new_details = {}
        self.pop_screen()

    @guarded
    async def create_new_script(
        self, widget: toga.Widget | None = None, **kwargs: Any
    ) -> None:
        """Ask for the script's details, then make it from the template."""
        await self.ask_new_details("Script", [("description", "Description")])

    @guarded
    async def create_new_project(
        self, widget: toga.Widget | None = None, **kwargs: Any
    ) -> None:
        """Ask for the project's details, then make it from the template."""
        await self.ask_new_details(
            "Project",
            [
                ("description", "Description"),
                ("bundle", "Bundle, such as com.example"),
                ("author", "Author"),
            ],
        )

    async def ask_new_details(self, kind: str, fields: list[tuple[str, str]]) -> None:
        """The details screen: everything but the name is optional."""
        typed = str(self.new_name.value) if self.new_name is not None else ""
        try:
            new_items.module_name(typed)
        except new_items.NameProblem as problem:
            await self.info(str(problem), "New")
            return
        self.new_details = {
            key: toga.TextInput(placeholder=label, flex=1) for key, label in fields
        }
        make = self.make_new_script if kind == "Script" else self.make_new_project
        rows: list[toga.Widget] = []
        for (key, label), field in zip(fields, self.new_details.values(), strict=True):
            rows += [toga.Label(label.split(",")[0]), toga.Box(children=[field])]
        self.push_screen(
            f"New {kind}",
            toga.Column(
                margin=8,
                children=[
                    toga.Row(children=[toga.Button("Back", on_press=self.back_new)]),
                    toga.Label(f"{new_items.title_of(typed)}: optional details"),
                    *rows,
                    toga.Label(
                        # Lines short enough for an iPhone SE in portrait
                        "Dependencies go in the file itself:\n"
                        "it has TODO comments saying where\n"
                        "(MyPyStub has no editor)."
                    ),
                    toga.Button(f"Create {kind}", on_press=make),
                ],
            ),
        )

    @guarded
    def back_new(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Back to the name, keeping what was typed there."""
        self.new_details = {}
        self.pop_screen()

    def detail(self, key: str) -> str:
        """What was typed in the details screen's `key` field, or ""."""
        field = self.new_details.get(key)
        return str(field.value) if field is not None else ""

    @guarded
    async def make_new_script(
        self, widget: toga.Widget | None = None, **kwargs: Any
    ) -> None:
        """Make the script, then show its Info."""
        await self.create_new(
            lambda folder, typed: new_items.create_script(
                folder, typed, self.detail("description")
            )
        )

    @guarded
    async def make_new_project(
        self, widget: toga.Widget | None = None, **kwargs: Any
    ) -> None:
        """Make the project, then show its Info."""
        await self.create_new(
            lambda folder, typed: new_items.create_project(
                folder,
                typed,
                self.detail("description"),
                self.detail("bundle"),
                self.detail("author"),
            )
        )

    async def create_new(self, make: Callable[[Path, str], Path]) -> None:
        """Make the new item with `make`, back to the list, and open its Info."""
        typed = str(self.new_name.value) if self.new_name is not None else ""
        try:
            made = make(self.get_current_dir(), typed)
        except new_items.NameProblem as problem:
            await self.info(str(problem), "New")
            return
        except new_items.TemplateProblem as problem:
            await self.error(str(problem), "Damaged template")
            return
        except OSError as error:
            await self.error(f"Couldn't create it: {error}", "New")
            return
        self.new_name = None
        self.new_details = {}
        self.pop_screen()  # the details
        self.pop_screen()  # the name
        self.reload_menu(self.script_list)
        await self.show_info_for(made)
