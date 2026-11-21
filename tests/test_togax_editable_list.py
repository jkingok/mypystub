"""togax_jkingok.EditableList, on Toga's dummy backend."""

import asyncio
import os
from typing import Any

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

from togax_jkingok import EditableList


def run(coro: Any) -> Any:
    """Run `coro` on a loop of its own, leaving the current loop alone."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def editor(items: list[str], **kwargs: Any) -> tuple[EditableList, list[list[str]]]:
    """An editor of `items`, recording each change."""
    changes: list[list[str]] = []
    made = EditableList(
        items,
        lambda i, item: {"title": item, "subtitle": f"Item {i + 1}"},
        on_change=lambda now: changes.append(list(now)),
        **kwargs,
    )
    return made, changes


def test_rows_show_the_items() -> None:
    made, _ = editor(["a", "b"])
    assert [row.title for row in made.list.data] == ["a", "b"]
    assert [row.subtitle for row in made.list.data] == ["Item 1", "Item 2"]


def test_buttons_need_a_selection() -> None:
    made, _ = editor(["a", "b"], movable=True)
    assert not made.buttons["delete"].enabled
    assert not any(b.enabled for b in made.move_buttons.values())
    made.selected = 0
    made.update_buttons()
    assert made.buttons["delete"].enabled
    assert made.move_buttons["down"].enabled and not made.move_buttons["up"].enabled


def test_moves_keep_the_selection_on_the_item() -> None:
    made, changes = editor(["a", "b", "c"], movable=True)
    made.selected = 0
    made.move_item("bottom")
    assert made.items == ["b", "c", "a"] and made.selected == 2
    assert changes == [["b", "c", "a"]]


def test_delete_removes_the_selected_item() -> None:
    made, changes = editor(["a", "b"])
    made.selected = 1
    made.delete_item()
    assert made.items == ["a"] and made.selected is None
    assert changes == [["a"]]


def test_add_and_edit_ask_the_owner() -> None:
    async def ask() -> str:
        return "new"

    async def change(item: str) -> str:
        return item.upper()

    made, changes = editor(["a"], on_add=ask, on_edit=change)
    run(made.add_item())
    assert made.items == ["a", "new"] and made.selected == 1
    run(made.edit_item())
    assert made.items == ["a", "NEW"]
    assert len(changes) == 2


def test_giving_up_changes_nothing() -> None:
    async def nothing(*args: Any) -> None:
        return None

    made, changes = editor(["a"], on_add=nothing, on_edit=nothing)
    made.selected = 0
    run(made.add_item())
    run(made.edit_item())
    assert made.items == ["a"] and changes == []


def test_without_handlers_there_is_no_add_or_edit_button() -> None:
    made, _ = editor(["a"])
    assert made.add_button.style.display == "none"
    assert made.buttons["edit"].style.display == "none"
    assert made.move_buttons == {}


def test_the_list_fits_its_rows_or_fills_when_the_box_flexes() -> None:
    sized, _ = editor(["a", "b"])
    assert sized.list.style.height == 120
    filling, _ = editor(["a", "b"], flex=1)
    assert filling.list.style.flex == 1
