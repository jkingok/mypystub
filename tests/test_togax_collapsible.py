"""Tests for togax_jkingok.Collapsible, on Toga's dummy backend."""

import os

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from togax_jkingok import Collapsible


def section(**kwargs: object) -> tuple[Collapsible, toga.Label]:
    """A section holding one label."""
    label = toga.Label("inside")
    return Collapsible("Things", [label], **kwargs), label  # type: ignore[arg-type]


def test_heading_is_a_bold_switch_above_the_body() -> None:
    box, label = section()
    assert box.children == [box.toggle, box.body]
    assert isinstance(box.toggle, toga.Switch)
    assert box.toggle.text == "Things" == box.title
    assert box.toggle.style.font_weight == "bold"
    assert box.body.children == [label]


def test_closed_by_default_and_open_when_asked() -> None:
    assert section()[0].body.style.display == "none"
    assert section(open=True)[0].body.style.display == "pack"


def test_toggling_shows_and_hides_the_body_and_reports_it() -> None:
    seen: list[bool] = []
    box, _ = section(on_change=lambda widget: seen.append(widget.open))
    box.open = True
    assert box.body.style.display == "pack" and box.shown
    box.toggle.value = False  # as the user would
    assert box.body.style.display == "none" and not box.shown
    assert seen == [True, False]


def test_a_section_with_nothing_to_show_stays_closed_even_when_on() -> None:
    box, _ = section(open=True, has_content=False)
    assert box.open and not box.shown
    assert box.body.style.display == "none"
    box.has_content = True
    assert box.body.style.display == "pack"


def test_the_title_can_change() -> None:
    box, _ = section()
    box.title = "Things (3)"
    assert box.toggle.text == "Things (3)"


def test_style_applies_to_the_whole_section() -> None:
    box, _ = section(flex=1)
    assert box.style.flex == 1
    assert box.style.direction == "column"
