"""togax_jkingok.lists: moving items, and the DetailedList helpers."""

from types import SimpleNamespace

import pytest

from togax_jkingok import lists
from togax_jkingok.lists import can_move, fit_list, list_height, move


@pytest.mark.parametrize(
    ("index", "where", "result", "new_index"),
    [
        (2, "top", ["c", "a", "b", "d"], 0),
        (2, "up", ["a", "c", "b", "d"], 1),
        (1, "down", ["a", "c", "b", "d"], 2),
        (1, "bottom", ["a", "c", "d", "b"], 3),
        (0, "up", ["a", "b", "c", "d"], 0),
        (3, "bottom", ["a", "b", "c", "d"], 3),
    ],
)
def test_moving_arguments(
    index: int, where: str, result: list[str], new_index: int
) -> None:
    """Arguments move in place; moving past an end leaves them as they are."""
    items = ["a", "b", "c", "d"]
    assert move(items, index, where) == new_index  # type: ignore[arg-type]
    assert items == result


def test_which_moves_are_possible() -> None:
    """Top and Up need a row above; Down and Bottom need a row below."""
    assert not can_move(3, None, "up")
    assert not can_move(3, 0, "top") and not can_move(3, 0, "up")
    assert can_move(3, 0, "down") and can_move(3, 0, "bottom")
    assert can_move(3, 2, "up") and not can_move(3, 2, "bottom")
    assert not can_move(1, 0, "up") and not can_move(1, 0, "down")


def test_a_list_is_sized_to_its_rows_up_to_a_few() -> None:
    assert list_height(0) == list_height(1) == lists.ROW_HEIGHT
    assert list_height(99) == lists.MOST_ROWS * lists.ROW_HEIGHT
    widget = SimpleNamespace(style=SimpleNamespace(height=None, display="pack"))
    fit_list(widget, 0)  # type: ignore[arg-type]
    assert widget.style.display == "none"
    fit_list(widget, 2)  # type: ignore[arg-type]
    assert widget.style.display == "pack" and widget.style.height == list_height(2)


def test_lists_keep_their_selection_when_their_screen_reappears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On iOS, a reappearing table must not clear the highlighted row."""
    native_controller = SimpleNamespace(clearsSelectionOnViewWillAppear=True)
    widget = SimpleNamespace(_impl=SimpleNamespace(native_controller=native_controller))
    lists.keep_selection(widget)  # type: ignore[arg-type]
    assert native_controller.clearsSelectionOnViewWillAppear  # not iOS: untouched
    monkeypatch.setattr(lists.sys, "platform", "ios")
    lists.keep_selection(widget)  # type: ignore[arg-type]
    assert native_controller.clearsSelectionOnViewWillAppear is False
