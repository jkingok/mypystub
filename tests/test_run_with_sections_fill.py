"""A form that fills the screen gives the room to its open sections only (#323)."""

from typing import Any

import pytest

pytest.importorskip("toga_dummy")

from mypystub.run_with import RunWithForm
from tests import support_ui  # noqa: F401 (selects the dummy backend)


async def never(*args: Any) -> Any:
    return None


def form() -> RunWithForm:
    """A package's form: no arguments, so only the environment fills it."""
    return RunWithForm(
        "pkg",
        args=None,
        env={},
        screens=None,  # type: ignore[arg-type]
        on_save=lambda settings: None,
        ask=never,
        tell=never,
        ask_fields=never,
    )


def test_an_open_section_flexes_and_a_closed_one_does_not() -> None:
    made = form()
    assert made.fill
    env = made.sections["env"]
    assert env.open and env.style.flex == 1 and env.body.style.flex == 1
    env.toggle.value = False
    assert env.style.flex == 0
    env.toggle.value = True
    assert env.style.flex == 1
