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
    SYSTEM,
    EnvRow,
    EnvValue,
    Layer,
    RunSettings,
    effective_rows,
    env_name_problem,
    env_value_problem,
)
from togax_jkingok import Collapsible, EditableList, refresh_on_new_width
from togax_jkingok.editable_list import ADD, DELETE, EDIT, GAP, tool
from togax_jkingok.lists import fit_list, keep_selection, select_row

# More toolbar symbols, beside EditableList's (the Help page says what each
# one does)
UNSET, VIEW = "⊘", "ⓘ"
# Labels don't wrap on iOS, so notes are broken to fit an iPhone SE
NOTE_WIDTH = 40


class Screens(Protocol):
    """Pushes screens over the launcher and pops them again."""

    def push_screen(
        self,
        title: str,
        content: toga.Widget,
        on_back: Callable[[], Any] | None = None,
    ) -> None:
        """Show `content` in place of the current screen; `on_back` is Back."""
        ...

    def pop_screen(self) -> None:
        """Go back to the screen before the last push."""
        ...


Ask = Callable[[str, str], Awaitable[bool]]
Tell = Callable[[str, str], Awaitable[None]]
AskFields = Callable[..., Awaitable[list[str] | None]]


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
        env: dict[str, EnvValue],
        inherited: Sequence[Layer] = (),
        screens: Screens,
        on_save: Callable[[RunSettings], None],
        ask: Ask,
        tell: Tell,
        ask_fields: AskFields,
        args_note: str | None = "Arguments are set on each entry point.",
        collapsible_sections: bool = True,
        screen_title: str | None = None,
        on_quick_start: Callable[[], Awaitable[bool]] | None = None,
        is_quick_start: bool = False,
        show_inherited: bool | None = None,
        on_show_inherited: Callable[[bool], None] | None = None,
        on_share: Callable[[], None] | None = None,
        backups: toga.Widget | None = None,
        workdir: str | None = None,
        inherited_workdir: tuple[str, str] | None = None,
        pick_workdir: Callable[[str | None], Awaitable[tuple[bool, str | None]]]
        | None = None,
        inherited_icon: Any = None,
    ) -> None:
        """Build the form; call :meth:`open` to show it.

        `on_quick_start`, for a runnable thing, makes it the one offered at
        launch; it returns whether it is now the Quick Start. `is_quick_start`
        is whether it already is. Inherited variables (the system's alone can be
        dozens, with long values) are hidden unless `show_inherited`; the switch
        that shows them calls `on_show_inherited`, so other screens can follow.
        `show_inherited` None means the user hasn't chosen yet: then they are
        shown when there are no variables of its own, so the screen isn't
        empty (#304). `inherited_icon`, if given, marks inherited rows in the
        list (a row's icon, see PrototypeBase.list_icon), and their second line
        is then just where they come from and the value.
        `args_note`, shown where the arguments would be, is left out when None.
        With `collapsible_sections` False the sections are always shown, with
        no heading of their own: for a screen whose title already names its
        one section (Setup's Environment).
        `backups`, if given, is the backup versions section (see
        :mod:`run_backups`), put above the buttons. `pick_workdir`, if given,
        adds the Working folder section (#308): `workdir` is this thing's own
        choice (None: inherited), `inherited_workdir` the choice it would
        inherit and where from, and `pick_workdir(current)` asks for a new one,
        returning whether it was changed and the choice (None to inherit). `on_share`, if given, adds a
        Share button that calls it (the share sheet is iOS only, so it is left out elsewhere).
        """
        self.title = title
        self.screen_title = screen_title or f"Setup · {title}"
        self.with_args = args is not None
        # The arguments' editor owns the list; the form saves it on each change
        self.args_editor = EditableList(
            list(args or []),
            lambda i, value: {"title": shown(value), "subtitle": f"Argument {i + 1}"},
            on_add=self._ask_arg,
            on_edit=self._ask_edit_arg,
            on_change=lambda items: self.changed(),
            movable=True,
        )
        self.args = self.args_editor.items
        self.env = dict(env)
        self.inherited = list(inherited)
        self.screens = screens
        self.on_save = on_save
        self.ask = ask
        self.tell = tell
        self.ask_fields = ask_fields
        self.on_quick_start = on_quick_start
        if show_inherited is None:
            show_inherited = not self.env and bool(self.inherited)
        self.show_inherited = show_inherited
        self.on_show_inherited = on_show_inherited
        self.inherited_icon = inherited_icon
        # With only the environment's list to show, it fills the screen
        # instead of sitting, sized to a few rows, in a scrolling column
        self.fill = args is None and backups is None
        self.on_share = on_share
        self.backups = backups  # the backup versions section, if there are any to show
        self.workdir = workdir
        self.inherited_workdir = inherited_workdir
        self.pick_workdir = pick_workdir
        self.workdir_label = toga.Label("", flex=1, margin=(0, 8))
        self._is_quick_start = is_quick_start
        self._qs_button: toga.Button | None = None
        self.share_button: toga.Button | None = None
        self.env_name: str | None = None
        self._refreshing = False
        self.collapsible_sections = collapsible_sections

        self.args_list = self.args_editor.list
        self.arg_buttons = self.args_editor.buttons
        self.move_buttons = self.args_editor.move_buttons
        self.move_row = self.args_editor.move_row
        self.args_tools = self.args_editor.toolbar
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
        keep_selection(self.env_list)
        # Each section's switch and the box it shows or hides, by name
        self.sections: dict[str, Collapsible] = {}
        self.button_row = toga.Row()
        self.scroll = toga.ScrollContainer()
        self.content = self._build(args_note)
        self.refresh()

    # -- Layout ---------------------------------------------------------------

    @staticmethod
    def _tool(symbol: str, on_press: Callable[..., Any]) -> toga.Button:
        return tool(symbol, on_press)

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
        """A section that its switch folds away; open when the form opens.

        Without collapsible sections it is just its children, always shown.
        """
        if not self.collapsible_sections:
            return list(children)
        section = Collapsible(
            title, children, open=True, on_change=self._toggle_section
        )
        self.sections[name] = section
        return [section]

    def _build(self, args_note: str | None) -> toga.Widget:
        children: list[toga.Widget] = []
        if self.with_args:
            children += self._section("args", "Arguments", [self.args_editor])
        elif args_note is not None:
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
        if self.pick_workdir is not None:
            children += self._section(
                "workdir",
                "Working folder",
                [
                    toga.Row(
                        align_items="center",
                        children=[
                            self.workdir_label,
                            toga.Button(
                                "Change…", on_press=self.change_workdir, margin=GAP
                            ),
                        ],
                    )
                ],
            )
        if self.backups is not None:
            children.append(self.backups)
        if self.fill:
            # The list scrolls itself, so nothing goes in a ScrollContainer
            self.env_list.style.flex = 1
            for section in self.sections.values():
                section.body.style.flex = 1
                self._fit_section(section)
            body_column = toga.Column(flex=1, children=children)
        else:
            self.scroll = toga.ScrollContainer(
                horizontal=False, flex=1, content=toga.Column(children=children)
            )
            if sys.platform == "ios":
                content = self.scroll.content
                assert content is not None
                refresh_on_new_width(
                    self.scroll._impl.document_container, content.refresh
                )
            body_column = self.scroll

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
        return toga.Column(flex=1, children=[body_column, self.button_row])

    @guarded
    def _toggle_section(self, section: Collapsible, **kwargs: Any) -> None:
        self._fit_section(section)

    def _fit_section(self, section: Collapsible) -> None:
        """Filling the screen, an open section shares the room; a closed one doesn't."""
        if self.fill:
            section.style.flex = 1 if section.shown else 0

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
        self.screens.push_screen(self.screen_title, self.content, on_back=self.done)

    # -- State ----------------------------------------------------------------

    def settings(self) -> RunSettings:
        """The settings as edited so far."""
        return RunSettings(list(self.args), dict(self.env), self.workdir)

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

    def row_data(self, row: EnvRow) -> dict[str, Any]:
        """A variable's list row: inherited ones marked by the icon, if there is one."""
        if row.inherited and self.inherited_icon is not None:
            value = "unset" if row.unset else shown(row.value)
            return {
                "icon": self.inherited_icon,
                "title": row.name,
                "subtitle": f"{row.source} · {value}",
            }
        return {"title": row.name, "subtitle": self.subtitle(row)}

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

    def workdir_text(self) -> str:
        """The Working folder line: the choice, and where it comes from if inherited."""
        from .workdirs import describe

        if self.workdir is not None:
            return describe(self.workdir)
        if self.inherited_workdir is None:
            return "Script's folder"
        choice, source = self.inherited_workdir
        return f"{describe(choice)} (from {source})"

    @guarded
    async def change_workdir(
        self, widget: toga.Widget | None = None, **kwargs: Any
    ) -> None:
        """Choose the working folder (#308)."""
        if self.pick_workdir is None:
            return
        changed, choice = await self.pick_workdir(self.workdir)
        if changed:
            self.workdir = choice
            self.changed()

    def changed(self) -> None:
        """Save the settings as they now are, then redraw."""
        self.on_save(self.settings())
        self.refresh()

    def refresh(self) -> None:
        """Redraw both lists and set which buttons can be pressed."""
        self._refreshing = True
        try:
            self.args_editor.refresh()
            rows = self.visible_rows()
            self.env_list.data = [self.row_data(row) for row in rows]
        finally:
            self._refreshing = False
        names = [row.name for row in rows]
        if self.env_name not in names:
            self.env_name = None
        select_row(
            self.env_list,
            names.index(self.env_name) if self.env_name is not None else None,
        )
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.workdir_label.text = self.workdir_text()
        if "args" in self.sections:
            self.sections["args"].title = f"Arguments ({len(self.args)})"

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
        if self.fill:
            self.env_list.style.display = "pack" if visible else "none"
        else:
            fit_list(self.env_list, visible)
        if "env" in self.sections:
            # The rows listed; they are still sorted A–Z
            self.sections["env"].title = f"Environment ({visible})"
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

    @property
    def arg_index(self) -> int | None:
        """The selected argument's index, if one is selected."""
        return self.args_editor.selected

    @arg_index.setter
    def arg_index(self, value: int | None) -> None:
        self.args_editor.selected = value

    @guarded
    async def _ask_arg(self) -> str | None:
        texts = await self.ask_fields("Add argument", "", [Field("Argument")])
        return None if texts is None else texts[0]

    @guarded
    async def _ask_edit_arg(self, value: str) -> str | None:
        texts = await self.ask_fields("Edit argument", "", [Field("Argument", value)])
        return None if texts is None else texts[0]

    @guarded
    async def add_arg(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Add an argument at the end."""
        await self.args_editor.add_item()

    @guarded
    async def edit_arg(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Change the selected argument."""
        await self.args_editor.edit_item()

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
