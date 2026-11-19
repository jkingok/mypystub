"""SafeArea: padding content clear of the notch, home indicator and keyboard."""

from __future__ import annotations

from typing import Any

import toga

from mypystub.safe_area import (
    NO_INSETS,
    Insets,
    SafeArea,
    SafeColumn,
    SafeRow,
    insets_for,
    scrolling_widgets,
)
from tests import support_ui  # noqa: F401 (selects the dummy backend)


def test_insets_without_a_keyboard_are_the_safe_area() -> None:
    """Landscape on a notched iPhone: the sides and the home indicator."""
    safe = Insets(0, 62, 21, 62)
    assert insets_for(safe, 300, 279) == Insets(0, 62, 21, 62)


def test_the_keyboard_raises_the_bottom() -> None:
    """The part of the box the keyboard covers is padded, not the safe bottom."""
    assert insets_for(Insets(0, 0, 34, 0), 700, 400) == Insets(0, 0, 300, 0)


def test_a_keyboard_below_the_box_changes_nothing() -> None:
    """A guide below the box (the keyboard doesn't reach it) leaves the safe area."""
    assert insets_for(Insets(0, 0, 0, 0), 500, 520) == NO_INSETS


def test_the_keyboard_can_be_ignored() -> None:
    assert insets_for(Insets(0, 0, 34, 0), 700, 400, keyboard=False) == Insets(
        0, 0, 34, 0
    )


def test_an_unlaid_box_ignores_the_keyboard() -> None:
    assert insets_for(Insets(0, 0, 34, 0), 0, 0) == Insets(0, 0, 34, 0)


def test_fractions_round_up() -> None:
    """Nothing is left a fraction of a point under an edge."""
    assert insets_for(Insets(0.5, 0, 20.1, 0), 100, 100) == Insets(1, 0, 21, 0)


def margins(widget: toga.Widget) -> tuple[float, float, float, float]:
    style = widget.style
    return (
        style.margin_top,
        style.margin_right,
        style.margin_bottom,
        style.margin_left,
    )


def test_it_is_a_box_with_boxs_arguments() -> None:
    """Children, id and style as Box takes them; nothing wrapped inside."""
    first, second = toga.Label("a"), toga.Label("b")
    area = SafeArea(id="tab", direction="column", children=[first, second])
    assert isinstance(area, toga.Box)
    assert area.id == "tab"
    assert area.children == [first, second]
    assert area.style.direction == "column"
    assert area.insets == NO_INSETS


def test_a_column_pads_its_first_and_last_child() -> None:
    top, middle, bottom = toga.Label("t"), toga.Label("m"), toga.Label("b")
    area = SafeArea(direction="column", children=[top, middle, bottom])
    area.set_insets(Insets(1, 2, 3, 4))
    assert margins(top) == (1, 2, 0, 4)
    assert margins(middle) == (0, 2, 0, 4)
    assert margins(bottom) == (0, 2, 3, 4)


def test_a_row_pads_its_first_and_last_child_across() -> None:
    left, right = toga.Label("l"), toga.Label("r")
    area = SafeArea(direction="row", children=[left, right])
    area.set_insets(Insets(1, 2, 3, 4))
    assert margins(left) == (1, 0, 3, 4)
    assert margins(right) == (1, 2, 3, 0)


def test_insets_add_to_a_childs_own_margin() -> None:
    child = toga.Label("x", margin=(5, 6, 7, 8))
    area = SafeArea(direction="column", children=[child])
    area.set_insets(Insets(1, 2, 3, 4))
    assert margins(child) == (6, 8, 10, 12)
    area.set_insets(NO_INSETS)
    assert margins(child) == (5, 6, 7, 8)


def test_children_that_move_are_padded_again() -> None:
    """A replaced or removed child gets its own margin back; the new edge gets the space."""
    output, activity, question = toga.Label("o"), toga.Label("a"), toga.Label("q")
    area = SafeArea(direction="column", children=[output, activity])
    area.set_insets(Insets(0, 0, 50, 0))
    assert margins(activity)[2] == 50
    area.replace(activity, question)
    assert margins(question)[2] == 50 and margins(activity) == (0, 0, 0, 0)
    area.remove(question)
    assert margins(output)[2] == 50 and margins(question) == (0, 0, 0, 0)
    area.add(activity)
    assert margins(activity)[2] == 50 and margins(output)[2] == 0


def test_on_change_reports_once() -> None:
    seen: list[Any] = []
    area = SafeArea(
        children=[toga.Box()], on_change=lambda box, insets: seen.append(insets)
    )
    area.set_insets(Insets(1, 2, 3, 4))
    area.set_insets(Insets(1, 2, 3, 4))
    assert seen == [Insets(1, 2, 3, 4)]
    assert area.insets == Insets(1, 2, 3, 4)


def test_the_keyboard_lets_scrolling_widgets_shrink() -> None:
    """Flexible scrolling widgets lose their minimum height only while it's up."""
    text = toga.MultilineTextInput(flex=1)
    fixed = toga.MultilineTextInput()  # flex 0: laid out at its minimum
    area = SafeArea(direction="column", children=[toga.TextInput(), text, fixed])
    area.set_insets(Insets(0, 0, 200, 0), keyboard_up=True)
    assert text._MIN_HEIGHT == 0
    assert fixed._MIN_HEIGHT == toga.MultilineTextInput._MIN_HEIGHT
    area.set_insets(NO_INSETS, keyboard_up=False)
    assert text._MIN_HEIGHT == toga.MultilineTextInput._MIN_HEIGHT
    assert "_MIN_HEIGHT" not in vars(text)


def test_scroll_container_content_is_left_alone() -> None:
    inner = toga.MultilineTextInput(flex=1)
    scroll = toga.ScrollContainer(content=toga.Column(children=[inner]), flex=1)
    found = scrolling_widgets(toga.Column(children=[scroll]))
    assert found == [scroll]


def test_squeezed_output_shows_its_newest_line(monkeypatch: Any) -> None:
    """A read-only text view is scrolled to the end when the keyboard squeezes it."""
    output = toga.MultilineTextInput(readonly=True, flex=1)
    editor = toga.MultilineTextInput(flex=1)
    scrolled: list[toga.Widget] = []
    for view in (output, editor):
        monkeypatch.setattr(view, "scroll_to_bottom", lambda v=view: scrolled.append(v))
    monkeypatch.setattr(toga.App, "app", None)  # no loop: scroll straight away
    area = SafeArea(direction="column", children=[output, editor])
    area.set_insets(Insets(0, 0, 200, 0), keyboard_up=True)
    assert scrolled == [output]


def test_safe_row_and_column_set_the_direction() -> None:
    """Shorthands, like toga.Row and toga.Column."""
    child = toga.Label("x")
    column = SafeColumn(children=[child])
    assert isinstance(column, SafeArea) and column.style.direction == "column"
    assert column.children == [child]
    assert SafeRow().style.direction == "row"
