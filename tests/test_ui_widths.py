"""Laying a tab's content out again once it has a width (mypystub.ui_widgets)."""

from types import SimpleNamespace

import pytest

pytest.importorskip("toga_dummy")

from mypystub.ui_widgets import refresh_on_new_width
from tests import support_ui  # noqa: F401 (selects the dummy backend)


def watched() -> tuple[SimpleNamespace, list[int]]:
    """A stand-in native container, and a list that grows with each refresh."""
    container = SimpleNamespace(width=0.0, on_native_layout=None)
    calls: list[int] = []
    refresh_on_new_width(container, lambda: calls.append(1))
    return container, calls


def test_the_first_real_width_refreshes() -> None:
    """A layout with no width yet waits; the width arriving refreshes."""
    container, calls = watched()
    container.on_native_layout(container)
    assert calls == []
    container.width = 375.0
    container.on_native_layout(container)
    assert calls == [1]


def test_the_same_width_doesnt_refresh_again() -> None:
    """A refresh causes a native layout, which mustn't refresh for ever."""
    container, calls = watched()
    container.width = 375.0
    container.on_native_layout(container)
    container.on_native_layout(container)
    assert calls == [1]


def test_rotation_refreshes() -> None:
    """A new width refreshes, and so does coming back to the old one."""
    container, calls = watched()
    for width in (375.0, 667.0, 375.0):
        container.width = width
        container.on_native_layout(container)
    assert len(calls) == 3
