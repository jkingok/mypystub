"""An empty Collapsible's switch is off and disabled, and comes back as chosen."""

import os

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from togax_jkingok import Collapsible


def section(**kwargs: object) -> Collapsible:
    return Collapsible("Things", [toga.Label("inside")], **kwargs)  # type: ignore[arg-type]


def test_with_nothing_to_show_the_switch_is_off_and_disabled() -> None:
    box = section(open=True, has_content=False)
    assert not box.toggle.enabled and not box.toggle.value
    assert box.body.style.display == "none" and not box.shown


def test_content_arriving_restores_the_choice() -> None:
    box = section(open=True, has_content=False)
    box.has_content = True
    assert box.toggle.enabled and box.toggle.value and box.shown
    closed = section(open=False, has_content=False)
    closed.has_content = True
    assert closed.toggle.enabled and not closed.toggle.value


def test_a_choice_made_with_content_survives_it_going_and_coming() -> None:
    box = section(open=True)
    box.toggle.value = False  # the user closes it
    box.has_content = False
    box.has_content = True
    assert not box.toggle.value and not box.shown


def test_the_empty_state_is_not_reported_as_a_user_change() -> None:
    seen: list[bool] = []
    box = section(open=True, on_change=lambda widget: seen.append(widget.open))
    box.has_content = False
    box.has_content = True
    assert seen == []  # no on_change for the section's own switch moves
    assert box.open


def test_opening_one_with_nothing_to_show_waits_for_content() -> None:
    box = section(has_content=False)
    box.open = True
    assert not box.toggle.value and not box.shown
    box.has_content = True
    assert box.toggle.value and box.shown
