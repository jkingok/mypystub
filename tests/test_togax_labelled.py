"""Tests for togax_jkingok's labelled widgets, on Toga's dummy backend."""

import os

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

from togax_jkingok import LabelledActivity, LabelledProgress, LabelledSelection


def test_progress_counts_up_to_its_limit() -> None:
    progress = LabelledProgress()
    progress.start(10)
    progress.update(3)
    assert progress.text.text == "3/10"
    progress.stop()
    assert progress.text.text == "10/10"


def test_progress_out_of_100_is_a_percentage() -> None:
    progress = LabelledProgress()
    progress.start(100)
    progress.update(30)
    assert progress.text.text == "30%"


def test_progress_without_a_limit_has_no_count() -> None:
    progress = LabelledProgress()
    progress.start()
    progress.update(5)
    assert progress.bar.max is None
    assert progress.text.text == ""


def test_activity_shows_its_text_and_spins_while_on() -> None:
    activity = LabelledActivity()
    activity.update("Working")
    assert activity.text.text == "Working"
    assert activity.activity.is_running
    activity.update("Done", on=False)
    assert not activity.activity.is_running


def test_selection_is_labelled_and_gives_its_value() -> None:
    selection = LabelledSelection("Page", items=["One", "Two"], value="Two")
    assert selection.children[0].text == "Page: "  # type: ignore[attr-defined]
    assert selection.value == "Two"
