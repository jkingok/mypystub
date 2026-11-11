"""errors/main_thread_error.py reports its error and then ends (#232).

Skipped where toga_dummy isn't installed, such as on device.
"""

import os
from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

import mypystub
from mypystub import ui
from tests.support_ui import run_to_end

EXAMPLE = (
    Path(mypystub.__file__).parent
    / "resources"
    / "examples"
    / "errors"
    / "main_thread_error.py"
)


def test_the_run_ends_after_the_main_thread_error(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The error reaches the loop's handler, and the script is not left waiting."""
    reported: list[BaseException | None] = []
    app.loop.set_exception_handler(
        lambda loop, ctx: reported.append(ctx.get("exception"))
    )
    try:
        run_to_end(proto, app, docs, EXAMPLE.read_text(), monkeypatch)
    finally:
        app.loop.set_exception_handler(None)
    assert proto.ended_run == proto.run_id
    assert [type(e) for e in reported] == [ValueError]
