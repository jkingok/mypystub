"""EditableList: a list the user adds to, edits, deletes from and reorders.

A DetailedList under a toolbar of symbol buttons that fit a phone's width:
⤒ ↑ ↓ ⤓ at the left (when the order matters) and + ✎ ⌫ at the right, each
enabled only when it can do something. The list owns its items; asking for a
new or changed item is left to the caller (`on_add`, `on_edit`), so any dialog
or screen can do it. Moves and deletes happen in place, the selection follows
the item, and `on_change` is called after every change. (The actions are
``add_item`` and so on, as ``add`` is already Toga's, for child widgets.)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import toga

from .lists import MOVES, Move, can_move, fit_list, keep_selection, move, select_row

# Monochrome symbols, not colour emoji: iOS greys out a disabled button by
# tinting its text, and emoji ignore the tint
MOVE_LABELS: dict[Move, str] = {"top": "⤒", "up": "↑", "down": "↓", "bottom": "⤓"}
ADD, EDIT, DELETE = "+", "✎", "⌫"
# Symbols are small at the default size
SYMBOL_SIZE = 22
# Space between toolbar buttons, so their labels don't run together
GAP = (0, 6)


def tool(symbol: str, on_press: Callable[..., Any]) -> toga.Button:
    """A toolbar button showing `symbol`."""
    return toga.Button(symbol, on_press=on_press, margin=GAP, font_size=SYMBOL_SIZE)


class EditableList(toga.Box):
    """A list of items with a toolbar to add, edit, delete and (optionally) move."""

    def __init__(
        self,
        items: list[Any],
        row: Callable[[int, Any], dict[str, Any]],
        *,
        on_add: Callable[[], Awaitable[Any | None]] | None = None,
        on_edit: Callable[[Any], Awaitable[Any | None]] | None = None,
        on_change: Callable[[list[Any]], None] | None = None,
        movable: bool = False,
        tools: Sequence[toga.Widget] = (),
        **kwargs: Any,
    ) -> None:
        """Edit `items` (in place), showing each as ``row(index, item)``.

        `on_add` and `on_edit` (given the item) ask for an item and return it,
        or None if the user gave up. `on_change` gets the items after any
        change. `movable` adds the move buttons. `tools` go after the others.
        `kwargs` style the whole box.
        """
        self.items = items
        self.row = row
        self.on_add = on_add
        self.on_edit = on_edit
        self.on_change = on_change
        self.selected: int | None = None
        self._refreshing = False
        self.list = toga.DetailedList(on_select=self._selected)
        keep_selection(self.list)
        self.buttons: dict[str, toga.Button] = {
            "edit": tool(EDIT, self.edit_item),
            "delete": tool(DELETE, self.delete_item),
        }
        self.move_buttons: dict[Move, toga.Button] = (
            {where: self._move_button(where) for where in MOVES} if movable else {}
        )
        self.move_row = toga.Row(children=list(self.move_buttons.values()))
        self.add_button = tool(ADD, self.add_item)
        self.add_button.style.display = "pack" if on_add else "none"
        self.buttons["edit"].style.display = "pack" if on_edit else "none"
        self.toolbar = toga.Row(
            align_items="center",
            margin=(0, 4),
            children=[
                self.move_row,
                toga.Box(flex=1),
                self.add_button,
                *self.buttons.values(),
                *tools,
            ],
        )
        super().__init__(
            direction="column", children=[self.toolbar, self.list], **kwargs
        )
        self.refresh()

    def _move_button(self, where: Move) -> toga.Button:
        return tool(MOVE_LABELS[where], lambda widget: self.move_item(where))

    def refresh(self) -> None:
        """Redraw the rows, keep the selection, and enable what can be pressed."""
        self._refreshing = True
        try:
            self.list.data = [self.row(i, item) for i, item in enumerate(self.items)]
        finally:
            self._refreshing = False
        if self.selected is not None and self.selected >= len(self.items):
            self.selected = None
        select_row(self.list, self.selected)
        if self.style.flex:
            self.list.style.flex = 1  # filling: the list scrolls itself
        else:
            fit_list(self.list, len(self.items))
        self.update_buttons()

    def update_buttons(self) -> None:
        """Enable the buttons that can do something now."""
        for button in self.buttons.values():
            button.enabled = self.selected is not None
        for where, button in self.move_buttons.items():
            button.enabled = can_move(len(self.items), self.selected, where)

    def changed(self) -> None:
        """Tell the owner, then redraw."""
        if self.on_change is not None:
            self.on_change(self.items)
        self.refresh()

    def _selected(self, widget: toga.DetailedList, **kwargs: Any) -> None:
        if self._refreshing:
            return
        row = widget.selection
        self.selected = None if row is None else widget.data.index(row)
        self.update_buttons()

    async def add_item(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Ask for an item, and add it at the end, selected."""
        if self.on_add is None:
            return
        item = await self.on_add()
        if item is not None:
            self.items.append(item)
            self.selected = len(self.items) - 1
            self.changed()

    async def edit_item(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Ask for a new version of the selected item."""
        index = self.selected
        if index is None or self.on_edit is None:
            return
        item = await self.on_edit(self.items[index])
        if item is not None and index < len(self.items):
            self.items[index] = item
            self.changed()

    def delete_item(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Remove the selected item."""
        if self.selected is None:
            return
        del self.items[self.selected]
        self.selected = None
        self.changed()

    def move_item(self, where: Move) -> None:
        """Move the selected item; the selection follows it."""
        if self.selected is None:
            return
        self.selected = move(self.items, self.selected, where)
        self.changed()
