"""Helpers for Toga's DetailedList: selection that sticks, sizing, and moves.

Toga's DetailedList can't show a selection it didn't make itself, and on iOS a
list clears its selection whenever its screen reappears. A list in a
ScrollContainer can't flex either, so it is sized to its rows. And a list whose
order matters needs its items moved to the top, up, down or to the bottom.
"""

from __future__ import annotations

import sys
from typing import Any, Literal

import toga

Move = Literal["top", "up", "down", "bottom"]
MOVES: tuple[Move, ...] = ("top", "up", "down", "bottom")

# A DetailedList row with a subtitle is about this tall; a list sized to its
# rows shows up to a few, and scrolls within that for more
ROW_HEIGHT = 60
# A row with only a title is about this tall
ONE_LINE_ROW_HEIGHT = 44
MOST_ROWS = 5


def can_move(length: int, index: int | None, where: Move) -> bool:
    """Whether the item at `index` can move `where` in a list of `length`."""
    if index is None or not 0 <= index < length:
        return False
    if where in ("top", "up"):
        return index > 0
    return index < length - 1


def move(items: list[Any], index: int, where: Move) -> int:
    """Move ``items[index]`` in place, returning its new index."""
    if not can_move(len(items), index, where):
        return index
    item = items.pop(index)
    new_index = {
        "top": 0,
        "up": index - 1,
        "down": index + 1,
        "bottom": len(items),
    }[where]
    items.insert(new_index, item)
    return new_index


def select_row(widget: toga.DetailedList, index: int | None) -> None:
    """Show `index` as selected; Toga's DetailedList can't do this itself.

    On iOS the native table is told directly. Elsewhere nothing is shown, so
    the caller keeps its own record of the selection.
    """
    if sys.platform != "ios" or index is None:
        return
    from toga_iOS.libs.foundation import NSIndexPath

    path = NSIndexPath.indexPathForRow(index, inSection=0)
    widget._impl.native.selectRowAtIndexPath(path, animated=False, scrollPosition=0)


def keep_selection(widget: toga.DetailedList) -> None:
    """Stop iOS clearing the list's selection whenever its screen reappears.

    toga_iOS drives DetailedList with a UITableViewController, whose
    clearsSelectionOnViewWillAppear defaults to YES.
    """
    if sys.platform == "ios":
        widget._impl.native_controller.clearsSelectionOnViewWillAppear = False


def list_height(rows: int, most: int = MOST_ROWS, row: int = ROW_HEIGHT) -> int:
    """The height of a list showing `rows` rows, at most `most` of them."""
    return max(1, min(rows, most)) * row


def fit_list(
    widget: toga.DetailedList,
    rows: int,
    most: int = MOST_ROWS,
    row: int = ROW_HEIGHT,
) -> None:
    """Size a list to its rows (each `row` high), or hide it when it has none."""
    widget.style.height = list_height(rows, most, row)
    widget.style.display = "pack" if rows else "none"
