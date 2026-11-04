"""The Setup form for one thing: command-line arguments and environment variables.

Swiping right on a script or project opens it. The form is a screen pushed in
place of the launcher, since Toga has no popover on iOS. Both lists work the
same way: a tap selects a row and the buttons act on it. Arguments keep their
order, which the move buttons change; environment variables are always
alphabetised, because their order doesn't matter. Every change is saved as it
is made, so the form only needs Done; running is left to a tap on the row.
"""

from __future__ import annotations

import sys
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol

import toga

from mypystub.prompts import Field
from mypystub.run_settings import (
    MOVES,
    EnvRow,
    Layer,
    Move,
    RunSettings,
    can_move,
    effective_rows,
    env_name_problem,
    env_value_problem,
    move,
)

# Toolbar-style buttons use symbols to fit a phone's width; the Help page
# says what each one does. Not colour emoji: iOS greys out a disabled button
# by tinting its text, and emoji ignore the tint
MOVE_LABELS: dict[Move, str] = {
    "top": "⤒",
    "up": "↑",
    "down": "↓",
    "bottom": "⤓",
}
ADD, EDIT, DELETE = "+", "✎", "⌫"
# Space between toolbar buttons, so their labels don't run together
GAP = (0, 6)
# Symbols are small at the default size
SYMBOL_SIZE = 22


class Screens(Protocol):
    """Pushes screens over the launcher and pops them again."""

    def push_screen(self, title: str, content: toga.Widget) -> None:
        """Show `content` in place of the current screen."""
        ...

    def pop_screen(self) -> None:
        """Go back to the screen before the last push."""
        ...


Ask = Callable[[str, str], Awaitable[bool]]
Tell = Callable[[str, str], Awaitable[None]]
AskFields = Callable[..., Awaitable[list[str] | None]]


def select_row(widget: toga.DetailedList, index: int | None) -> None:
    """Show `index` as selected; Toga's DetailedList can't do this itself.

    On iOS the native table is told directly. Elsewhere nothing is shown, but
    the form keeps its own record of the selection, so the buttons still work.
    """
    if sys.platform != "ios" or index is None:
        return
    from toga_iOS.libs.foundation import NSIndexPath

    path = NSIndexPath.indexPathForRow(index, inSection=0)
    widget._impl.native.selectRowAtIndexPath(path, animated=False, scrollPosition=0)


def keep_selection(widget: toga.DetailedList) -> None:
    """Stop iOS clearing the list's selection whenever its screen reappears.

    toga_iOS drives DetailedList with a UITableViewController, whose
    clearsSelectionOnViewWillAppear defaults to YES, so the highlight was lost
    each time the form came back from an editor.
    """
    if sys.platform == "ios":
        widget._impl.native_controller.clearsSelectionOnViewWillAppear = False


def shown(value: str) -> str:
    """A value as a list row shows it, so empty values are still visible."""
    return value if value else "(empty)"


class RunWithForm:
    """Edit the arguments and own environment variables of one thing.

    `args` is None for things whose arguments are set elsewhere (a package
    with several entry points, or Setup), and then only the environment is
    shown. `inherited` are the outer layers, outermost first. `on_save` is
    called with the settings after every change.
    """

    def __init__(
        self,
        title: str,
        *,
        args: Sequence[str] | None,
        env: dict[str, str],
        inherited: Sequence[Layer] = (),
        screens: Screens,
        on_save: Callable[[RunSettings], None],
        ask: Ask,
        tell: Tell,
        ask_fields: AskFields,
        args_note: str = "Arguments are set on each entry point.",
        screen_title: str | None = None,
    ) -> None:
        """Build the form; call :meth:`open` to show it."""
        self.title = title
        self.screen_title = screen_title or f"Setup · {title}"
        self.with_args = args is not None
        self.args = list(args or [])
        self.env = dict(env)
        self.inherited = list(inherited)
        self.screens = screens
        self.on_save = on_save
        self.ask = ask
        self.tell = tell
        self.ask_fields = ask_fields
        self.arg_index: int | None = None
        self.env_name: str | None = None
        self._refreshing = False

        self.args_list = toga.DetailedList(on_select=self._arg_selected, flex=1)
        self.args_empty = toga.Label("No arguments", margin=(0, 8))
        self.arg_buttons = {
            "edit": self._tool(EDIT, self.edit_arg),
            "delete": self._tool(DELETE, self.delete_arg),
        }
        self.move_buttons: dict[Move, toga.Button] = {
            where: self._move_button(where) for where in MOVES
        }
        self.env_list = toga.DetailedList(on_select=self._env_selected, flex=1)
        self.env_empty = toga.Label("No environment variables", margin=(0, 8))
        self.env_note = toga.Label("", margin=(0, 8))
        self.env_buttons = {
            "edit": self._tool(EDIT, self.edit_env),
            "delete": self._tool(DELETE, self.delete_env),
        }
        keep_selection(self.args_list)
        keep_selection(self.env_list)
        self.content = self._build(args_note)
        self.refresh()

    # -- Layout ---------------------------------------------------------------

    def _move_button(self, where: Move) -> toga.Button:
        return toga.Button(
            MOVE_LABELS[where],
            on_press=lambda w: self.move_arg(where),
            flex=1,
            font_size=SYMBOL_SIZE,
        )

    @staticmethod
    def _tool(symbol: str, on_press: Callable[..., Any]) -> toga.Button:
        return toga.Button(symbol, on_press=on_press, margin=GAP, font_size=SYMBOL_SIZE)

    def _header(self, label: str, add: Callable[..., Any], buttons: dict) -> toga.Box:
        return toga.Row(
            align_items="center",
            margin=(8, 4, 0, 8),
            children=[
                toga.Label(label, font_weight="bold", flex=1),
                self._tool(ADD, add),
                buttons["edit"],
                buttons["delete"],
            ],
        )

    def _build(self, args_note: str) -> toga.Widget:
        children: list[toga.Widget] = []
        if self.with_args:
            children += [
                self._header("Arguments", self.add_arg, self.arg_buttons),
                self.args_list,
                self.args_empty,
                toga.Row(margin=(0, 4), children=list(self.move_buttons.values())),
            ]
        else:
            children.append(toga.Label(args_note, margin=(8, 8, 0, 8)))
        children += [
            self._header("Environment (A–Z)", self.add_env, self.env_buttons),
            self.env_list,
            self.env_empty,
            self.env_note,
        ]
        children.append(
            toga.Row(
                margin=4,
                children=[
                    toga.Box(flex=1),
                    toga.Button("Done", on_press=self.done, margin=GAP),
                ],
            )
        )
        return toga.Column(flex=1, children=children)

    def open(self) -> None:
        """Show the form over the current screen."""
        self.screens.push_screen(self.screen_title, self.content)

    # -- State ----------------------------------------------------------------

    def settings(self) -> RunSettings:
        """The settings as edited so far."""
        return RunSettings(list(self.args), dict(self.env))

    def env_rows(self) -> list[EnvRow]:
        """The variables in effect here, alphabetised, inherited ones marked."""
        return effective_rows(self.inherited, self.env)

    def selected_env(self) -> EnvRow | None:
        """The selected environment row, if any."""
        return next((r for r in self.env_rows() if r.name == self.env_name), None)

    def changed(self) -> None:
        """Save the settings as they now are, then redraw."""
        self.on_save(self.settings())
        self.refresh()

    def refresh(self) -> None:
        """Redraw both lists and set which buttons can be pressed."""
        self._refreshing = True
        try:
            self.args_list.data = [
                {"title": shown(value), "subtitle": f"Argument {i + 1}"}
                for i, value in enumerate(self.args)
            ]
            rows = self.env_rows()
            self.env_list.data = [
                {
                    "title": row.name,
                    "subtitle": shown(row.value)
                    + (f" · from {row.source}" if row.source else ""),
                }
                for row in rows
            ]
        finally:
            self._refreshing = False
        if self.arg_index is not None and self.arg_index >= len(self.args):
            self.arg_index = None
        names = [row.name for row in rows]
        if self.env_name not in names:
            self.env_name = None
        select_row(self.args_list, self.arg_index)
        select_row(
            self.env_list,
            names.index(self.env_name) if self.env_name is not None else None,
        )
        self._update_buttons()

    def _update_buttons(self) -> None:
        has_arg = self.arg_index is not None
        for button in self.arg_buttons.values():
            button.enabled = has_arg
        for where, button in self.move_buttons.items():
            button.enabled = can_move(len(self.args), self.arg_index, where)
        self.args_empty.style.visibility = "hidden" if self.args else "visible"

        row = self.selected_env()
        self.env_buttons["edit"].enabled = row is not None
        self.env_buttons["delete"].enabled = row is not None and not row.inherited
        self.env_empty.style.visibility = "hidden" if self.env_rows() else "visible"
        if row is not None and row.inherited:
            self.env_note.text = (
                f"{row.name} is set in {row.source}. Edit it to override it here,"
                f" or change it in {row.source}."
            )
        elif row is not None and any(row.name in layer.env for layer in self.inherited):
            self.env_note.text = (
                f"{row.name} overrides an inherited value. Delete it to use that"
                " value again."
            )
        else:
            self.env_note.text = ""

    def _arg_selected(self, widget: toga.DetailedList, **kwargs: Any) -> None:
        if self._refreshing:
            return
        row = widget.selection
        self.arg_index = None if row is None else widget.data.index(row)
        self._update_buttons()

    def _env_selected(self, widget: toga.DetailedList, **kwargs: Any) -> None:
        if self._refreshing:
            return
        row = widget.selection
        self.env_name = None if row is None else str(getattr(row, "title", ""))
        self._update_buttons()

    # -- Arguments ------------------------------------------------------------

    async def add_arg(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Add an argument at the end."""
        texts = await self.ask_fields("Add argument", "", [Field("Argument")])
        if texts is not None:
            self.args.append(texts[0])
            self.arg_index = len(self.args) - 1
            self.changed()

    async def edit_arg(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Change the selected argument."""
        index = self.arg_index
        if index is None:
            return
        texts = await self.ask_fields(
            "Edit argument", "", [Field("Argument", self.args[index])]
        )
        if texts is not None and index < len(self.args):
            self.args[index] = texts[0]
            self.changed()

    def delete_arg(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Remove the selected argument."""
        if self.arg_index is None:
            return
        del self.args[self.arg_index]
        self.arg_index = None
        self.changed()

    def move_arg(self, where: Move) -> None:
        """Move the selected argument; the selection follows it."""
        if self.arg_index is None:
            return
        self.arg_index = move(self.args, self.arg_index, where)
        self.changed()

    # -- Environment ----------------------------------------------------------

    async def add_env(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Add a variable here."""
        await self._edit_env("Add variable", "", "")

    async def edit_env(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Change the selected variable; an inherited one gets an override here."""
        row = self.selected_env()
        if row is not None:
            await self._edit_env("Edit variable", row.name, row.value, original=row)

    def delete_env(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Remove this layer's value; an inherited value shows again."""
        row = self.selected_env()
        if row is None or row.inherited:
            return
        del self.env[row.name]
        self.changed()

    async def set_env(self, name: str, value: str, original: EnvRow | None) -> bool:
        """Store a variable from the editor; False if it was refused."""
        if problem := env_name_problem(name):
            await self.tell("Variable name", problem)
            return False
        if problem := env_value_problem(value):
            await self.tell("Variable value", problem)
            return False
        renamed = original is None or name != original.name
        if renamed and name in self.env:
            replace = await self.ask(
                "Replace variable?",
                f"{name} is already set here to “{self.env[name]}”. Replace it?",
            )
            if not replace:
                return False
        if original is not None and renamed and not original.inherited:
            del self.env[original.name]
        self.env[name] = value
        self.env_name = name
        self.changed()
        return True

    async def _edit_env(
        self, title: str, name: str, value: str, original: EnvRow | None = None
    ) -> None:
        """Ask for a name and value until they're accepted or it's cancelled."""
        while True:
            texts = await self.ask_fields(
                title, "", [Field("Name", name), Field("Value", value)]
            )
            if texts is None:
                return
            name, value = texts
            if await self.set_env(name, value, original):
                return

    # -- Finishing ------------------------------------------------------------

    def done(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Go back; changes were already saved as they were made."""
        self.screens.pop_screen()
