"""LabelledActivity's count: a progress bar once the work's size is known."""

import os

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

from togax_jkingok import LabelledActivity


def test_no_count_until_one_is_given() -> None:
    activity = LabelledActivity()
    activity.update("Working")
    assert not activity.counting
    assert activity.progress.style.display == "none"


def test_counting_shows_the_bar_and_how_far_it_has_got() -> None:
    activity = LabelledActivity()
    activity.update("Checking")
    activity.count(3, 10)
    assert activity.counting
    assert activity.progress.bar.value == 3
    assert activity.progress.text.text == "3/10"


def test_a_new_total_starts_again() -> None:
    activity = LabelledActivity()
    activity.count(4, 4)
    activity.count(0, 2)
    assert activity.progress.bar.max == 2
    assert activity.progress.text.text == "0/2"


def test_stopping_the_activity_takes_the_count_away() -> None:
    activity = LabelledActivity()
    activity.count(1, 5)
    activity.update("Done", on=False)
    assert not activity.counting
    assert activity.text.text == "Done"


def test_nothing_to_count_shows_no_bar() -> None:
    activity = LabelledActivity()
    activity.count(0, 0)
    assert not activity.counting


def test_the_bar_sits_under_the_text_beside_the_indicator() -> None:
    """Row -> [indicator, Column -> [text, bar]], so it fits a narrow phone."""
    activity = LabelledActivity()
    assert activity.children == [activity.activity, activity.column]
    assert activity.column.children == [activity.text, activity.progress]
    assert activity.column.style.flex == 1
    assert activity.progress.style.width in ("none", None)  # the column's width
