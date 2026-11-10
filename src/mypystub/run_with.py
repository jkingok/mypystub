"""The Setup form for one thing: command-line arguments and environment variables.

Swiping right on a script or project opens it. The form is a screen pushed in
place of the launcher, since Toga has no popover on iOS. Both lists work the
same way: a tap selects a row and the buttons act on it. Arguments keep their
order, which the move buttons change; environment variables are always
alphabetised, because their order doesn't matter. Every change is saved as it
is made, so the form only needs Done; running is left to a tap on the row.

The sections scroll above a fixed row of buttons, so the buttons stay on screen
however long the sections get, and each section folds away under a switch.
"""

from __future__ import annotations

import asyncio
import sys
import textwrap
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol

import toga

from mypystub.errors import guarded
from mypystub.prompts import Field
from mypystub.run_settings import (
    MOVES,
    SYSTEM,
    EnvRow,
    EnvValue,
    Layer,
    Move,
    RunSettings,
    can_move,
    effective_rows,
    env_name_problem,
    env_value_problem,
    move,
)
from mypystub.ui_widgets import refresh_on_new_width

# Toolbar-style buttons use symbols to fit a phone's width; the Help page
# says what each one does. Not colour emoji: iOS greys out a disabled button
# by tinting its text, and emoji ignore the tint
MOVE_LABELS: dict[Move, str] = {
    "top": "⤒",
    "up": "↑",
    "down": "↓",
    "bottom": "⤓",
}
ADD, EDIT, DELETE, UNSET, VIEW = "+", "✎", "⌫", "⊘", "ⓘ"
# Space between toolbar buttons, so their labels don't run together
GAP = (0, 6)
# Symbols are small at the default size
SYMBOL_SIZE = 22
# Labels don't wrap on iOS, so notes are broken to fit an iPhone SE
NOTE_WIDTH = 40
# A list can't flex inside a ScrollContainer, so it is sized to its rows (a
# DetailedList row with a subtitle is about this tall), up to a few rows; a
# longer list scrolls within that
ROW_HEIGHT = 60
MOST_ROWS = 5


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


def list_height(rows: int) -> int:
    """The height of a list showing `rows` rows, at most MOST_ROWS of them."""
    return max(1, min(rows, MOST_ROWS)) * ROW_HEIGHT


def fit_list(rows_list: toga.DetailedList, rows: int) -> None:
    """Size a list to its rows, or hide it when it has none.

    The section's title gives the count, so an empty list needs no label.
    """
    rows_list.style.height = list_height(rows)
    rows_list.style.display = "pack" if rows else "none"


def collapsible(
    title: str,
    children: Sequence[toga.Widget],
    *,
    open: bool,
    on_change: Callable[..., Any],
) -> tuple[toga.Switch, toga.Box]:
    """A section's switch, and the box of `children` it shows or hides.

    The caller's `on_change` should call :func:`show_body`, after anything else
    it does.
    """
    switch = toga.Switch(
        title, value=open, on_change=on_change, margin=(8, 8, 0, 8), font_weight="bold"
    )
    body = toga.Column(children=list(children))
    show_body(switch, body)
    return switch, body


def show_body(switch: toga.Switch, body: toga.Widget, has_rows: bool = True) -> None:
    """Show `body` while its switch is on (and it has anything to show)."""
    body.style.display = "pack" if switch.value and has_rows else "none"


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
        env: dict[str, EnvValue],
        inherited: Sequence[Layer] = (),
        screens: Screens,
        on_save: Callable[[RunSettings], None],
        ask: Ask,
        tell: Tell,
        ask_fields: AskFields,
        args_note: str = "Arguments are set on each entry point.",
        screen_title: str | None = None,
        on_quick_start: Callable[[], Awaitable[bool]] | None = None,
        is_quick_start: bool = False,
        show_inherited: bool = False,
        on_show_inherited: Callable[[bool], None] | None = None,
        on_share: Callable[[], None] | None = None,
        backups: toga.Widget | None = None,
    ) -> None:
        """Build the form; call :meth:`open` to show it.

        `on_quick_start`, for a runnable thing, makes it the one offered at
        launch; it returns whether it is now the Quick Start. `is_quick_start`
        is whether it already is. Inherited variables (the system's alone can be
        dozens, with long values) are hidden unless `show_inherited`; the switch
        that shows them calls `on_show_inherited`, so other screens can follow.
        `backups`, if given, is the backup versions section (see
        :mod:`run_backups`), put above the buttons. `on_share`, if given, adds a
        Share button that calls it (the share sheet is iOS only, so it is left out elsewhere).
        """
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
        self.on_quick_start = on_quick_start
        self.show_inherited = show_inherited
        self.on_show_inherited = on_show_inherited
        self.on_share = on_share
        self.backups = backups  # the backup versions section, if there are any to show
        self._is_quick_start = is_quick_start
        self._qs_button: toga.Button | None = None
        self.share_button: toga.Button | None = None
        self.arg_index: int | None = None
        self.env_name: str | None = None
        self._refreshing = False

        self.args_list = toga.DetailedList(on_select=self._arg_selected)
        self.arg_buttons = {
            "edit": self._tool(EDIT, self.edit_arg),
            "delete": self._tool(DELETE, self.delete_arg),
        }
        self.move_buttons: dict[Move, toga.Button] = {
            where: self._move_button(where) for where in MOVES
        }
        self.env_list = toga.DetailedList(on_select=self._env_selected)
        self.env_note = toga.Label("", margin=(0, 8))
        self.env_buttons = {
            "edit": self._tool(EDIT, self.edit_env),
            "delete": self._tool(DELETE, self.delete_env),
            "unset": self._tool(UNSET, self.unset_env),
            "view": self._tool(VIEW, self.view_env),
        }
        self.inherited_switch: toga.Switch | None = (
            toga.Switch(
                "Show inherited variables",
                value=show_inherited,
                on_change=self._toggle_inherited,
                margin=(0, 8),
            )
            if self.inherited
            else None
        )
        keep_selection(self.args_list)
        keep_selection(self.env_list)
        # Each section's switch and the box it shows or hides, by name
        self.sections: dict[str, tuple[toga.Switch, toga.Box]] = {}
        self.button_row = toga.Row()
        self.scroll = toga.ScrollContainer()
        self.content = self._build(args_note)
        self.refresh()

    # -- Layout ---------------------------------------------------------------

    def _move_button(self, where: Move) -> toga.Button:
        return toga.Button(
            MOVE_LABELS[where],
            on_press=lambda w: self.move_arg(where),
            margin=GAP,
            font_size=SYMBOL_SIZE,
        )

    @staticmethod
    def _tool(symbol: str, on_press: Callable[..., Any]) -> toga.Button:
        return toga.Button(symbol, on_press=on_press, margin=GAP, font_size=SYMBOL_SIZE)

    def _toolbar(
        self,
        add: Callable[..., Any],
        buttons: dict,
        lead: Sequence[toga.Widget] = (),
    ) -> toga.Box:
        """A section's buttons under its switch: `lead` at the left, the rest right.

        An empty box flexes between them, pushing each group to its side.
        """
        return toga.Row(
            align_items="center",
            margin=(0, 4),
            children=[
                *lead,
                toga.Box(flex=1),
                self._tool(ADD, add),
                *buttons.values(),
            ],
        )

    def _section(
        self, name: str, title: str, children: Sequence[toga.Widget]
    ) -> list[toga.Widget]:
        """A section that its switch folds away; open when the form opens."""
        switch, body = collapsible(
            title, children, open=True, on_change=self._toggle_section
        )
        self.sections[name] = (switch, body)
        return [switch, body]

    def _build(self, args_note: str) -> toga.Widget:
        children: list[toga.Widget] = []
        if self.with_args:
            # One row saves space: moves at the left, add/edit/delete at the right
            self.move_row = toga.Row(children=list(self.move_buttons.values()))
            self.args_tools = self._toolbar(
                self.add_arg, self.arg_buttons, lead=[self.move_row]
            )
            children += self._section(
                "args", "Arguments", [self.args_tools, self.args_list]
            )
        else:
            children.append(toga.Label(args_note, margin=(8, 8, 0, 8)))
        self.env_tools = self._toolbar(self.add_env, self.env_buttons)
        children += self._section(
            "env",
            "Environment",
            [
                self.env_tools,
                *([self.inherited_switch] if self.inherited_switch is not None else []),
                self.env_list,
                self.env_note,
            ],
        )
        if self.backups is not None:
            children.append(self.backups)
        self.scroll = toga.ScrollContainer(
            horizontal=False, flex=1, content=toga.Column(children=children)
        )
        if sys.platform == "ios":
            content = self.scroll.content
            assert content is not None
            refresh_on_new_width(self.scroll._impl.document_container, content.refresh)

        # The buttons share the row's width and stay put below the scrolling part
        bottom: list[toga.Widget] = []
        if self.on_quick_start is not None:
            bottom.append(self._quick_start_button())
        if self.on_share is not None:
            self.share_button = toga.Button(
                "Share", on_press=self._press_share, margin=GAP, flex=1
            )
            bottom.append(self.share_button)
        bottom.append(toga.Button("Done", on_press=self.done, margin=GAP, flex=1))
        self.button_row = toga.Row(margin=4, children=bottom)
        return toga.Column(flex=1, children=[self.scroll, self.button_row])

    @guarded
    def _toggle_section(self, widget: toga.Switch, **kwargs: Any) -> None:
        for switch, body in self.sections.values():
            if switch is widget:
                show_body(switch, body)

    def _quick_start_button(self) -> toga.Button:
        """The button that makes this thing the launch Quick Start."""
        self._qs_button = toga.Button(
            "Quick Start ✓" if self._is_quick_start else "Make Quick Start",
            on_press=self._press_quick_start,
            margin=GAP,
            flex=1,
            enabled=not self._is_quick_start,
        )
        return self._qs_button

    @guarded
    def _press_share(self, widget: toga.Widget | None = None, **_: Any) -> None:
        if self.on_share is not None:
            self.on_share()

    @guarded
    def _press_quick_start(self, widget: toga.Widget | None = None, **_: Any) -> None:
        asyncio.ensure_future(self._run_quick_start())

    async def _run_quick_start(self) -> None:
        if self.on_quick_start is None or not await self.on_quick_start():
            return
        self._is_quick_start = True
        if self._qs_button is not None:
            self._qs_button.text = "Quick Start ✓"
            self._qs_button.enabled = False

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

    def visible_rows(self) -> list[EnvRow]:
        """The variables the list shows: inherited ones only if they're switched on.

        A variable this layer sets or unsets itself always shows, even when it
        overrides an inherited one.
        """
        rows = self.env_rows()
        if self.show_inherited:
            return rows
        return [row for row in rows if not row.inherited]

    def subtitle(self, row: EnvRow) -> str:
        """A row's second line: an inherited one says where it comes from first.

        The origin leads because the value can be long (PATH) and is cut off.
        A variable set here is just its value.
        """
        value = "(unset)" if row.unset else shown(row.value)
        return f"from {row.source} · {value}" if row.inherited else value

    @guarded
    def _toggle_inherited(self, widget: toga.Switch, **kwargs: Any) -> None:
        self.show_inherited = bool(widget.value)
        if self.on_show_inherited is not None:
            self.on_show_inherited(self.show_inherited)
        self.refresh()

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
            rows = self.visible_rows()
            self.env_list.data = [
                {"title": row.name, "subtitle": self.subtitle(row)} for row in rows
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
        fit_list(self.args_list, len(self.args))
        if "args" in self.sections:
            self.sections["args"][0].text = f"Arguments ({len(self.args)})"

        row = self.selected_env()
        self.env_buttons["edit"].enabled = row is not None
        self.env_buttons["delete"].enabled = row is not None and not row.inherited
        self.env_buttons["unset"].enabled = row is not None and not row.unset
        hidden = len(self.env_rows()) - len(self.visible_rows())
        if self.inherited_switch is not None:
            self.inherited_switch.text = "Show inherited variables" + (
                f" ({hidden} hidden)" if hidden and not self.show_inherited else ""
            )
        visible = len(self.visible_rows())
        fit_list(self.env_list, visible)
        if "env" in self.sections:
            # The rows listed; they are still sorted A–Z
            self.sections["env"][0].text = f"Environment ({visible})"
        self.env_note.style.display = "pack" if row is not None else "none"
        self.env_buttons["view"].enabled = row is not None
        if row is not None and row.inherited and row.source == SYSTEM:
            note = (
                f"{row.name} comes from the system. Edit it to override it here"
                f" (even to blank), or use {UNSET} to unset it."
            )
        elif row is not None and row.inherited:
            note = (
                f"{row.name} is set in {row.source}. Edit it to override it here,"
                f" use {UNSET} to unset it, or change it in {row.source}."
            )
        elif row is not None and row.unset:
            note = (
                f"{row.name} is unset here: it won't exist when this runs. Edit it"
                " to give it a value, or delete this to use the inherited value."
            )
        elif row is not None and any(row.name in layer.env for layer in self.inherited):
            note = (
                f"{row.name} overrides an inherited value. Delete it to use that"
                " value again."
            )
        else:
            note = ""
        self.env_note.text = textwrap.fill(note, NOTE_WIDTH)

    @guarded
    def _arg_selected(self, widget: toga.DetailedList, **kwargs: Any) -> None:
        if self._refreshing:
            return
        row = widget.selection
        self.arg_index = None if row is None else widget.data.index(row)
        self._update_buttons()

    @guarded
    def _env_selected(self, widget: toga.DetailedList, **kwargs: Any) -> None:
        if self._refreshing:
            return
        row = widget.selection
        self.env_name = None if row is None else str(getattr(row, "title", ""))
        self._update_buttons()

    async def report_error(self, error: Exception, where: str) -> None:
        """Tell the user about an error that a handler raised (see errors.guarded)."""
        await self.tell("Error", f"{type(error).__name__}: {error}\n\n(in {where})")

    # -- Arguments ------------------------------------------------------------

    @guarded
    async def add_arg(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Add an argument at the end."""
        texts = await self.ask_fields("Add argument", "", [Field("Argument")])
        if texts is not None:
            self.args.append(texts[0])
            self.arg_index = len(self.args) - 1
            self.changed()

    @guarded
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

    @guarded
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

    @guarded
    async def add_env(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Add a variable here."""
        await self._edit_env("Add variable", "", "")

    @guarded
    async def edit_env(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Change the selected variable; an inherited one gets an override here."""
        row = self.selected_env()
        if row is not None:
            await self._edit_env("Edit variable", row.name, row.value, original=row)

    @guarded
    async def view_env(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Show the selected variable in full: its value can be too long for the row."""
        row = self.selected_env()
        if row is None:
            return
        origin = f"From {row.source}." if row.inherited else "Set here."
        value = (
            "(unset: it won't exist when this runs)"
            if row.unset
            else (row.value or "(empty)")
        )
        await self.tell(row.name, f"{origin}\n\n{value}")

    @guarded
    def unset_env(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Make the selected variable not exist when this runs."""
        row = self.selected_env()
        if row is None or row.unset:
            return
        self.env[row.name] = None
        self.changed()

    @guarded
    def delete_env(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Remove this layer's value; an inherited value shows again."""
        row = self.selected_env()
        if row is None or row.inherited:
            return
        del self.env[row.name]
        self.changed()

    def shown_here(self, name: str) -> str:
        """How this layer has a variable, for a question: set to “x”, or unset."""
        value = self.env[name]
        return "unset" if value is None else f"set to “{value}”"

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
                f"{name} is already {self.shown_here(name)} here. Replace it?",
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

    @guarded
    def done(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Go back; changes were already saved as they were made."""
        self.screens.pop_screen()
