"""A failure when tapping a row must show a dialog, not only reach the log.

Skipped where toga_dummy isn't installed, such as on device.
"""

import os
from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import ui
from tests.support_ui import tap


def test_failure_before_a_run_starts_is_shown(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the run can't even be set up, the user is told (it was once only logged)."""
    shown: list[tuple[str, str]] = []

    async def error(text: str, title: str | None = None) -> None:
        shown.append((title or "", text))

    def broken(selected: object) -> None:
        raise KeyError("run_with")

    monkeypatch.setattr(proto, "error", error)
    monkeypatch.setattr(proto, "run_settings_for", broken)
    tap(proto, "top", monkeypatch, app)
    assert len(shown) == 1
    assert shown[0][0] == "Error"
    assert "KeyError" in shown[0][1] and "run_with" in shown[0][1]
    assert proto.tabs.current_tab.text == "List"
