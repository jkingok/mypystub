"""input() and getpass() ask at the bottom of the Script tab, in the activity row's place.

At a terminal the question follows the output. The tab's SafeArea keeps the
tab above the keyboard on iOS, so the question can go at the bottom; while it
asks, the activity row gives up its place, leaving the output the rest.
"""

from pathlib import Path

import pytest
import toga

from mypystub import ui
from tests.support_ui import tap, wait_for


def last_row(proto: ui.Prototype) -> toga.Widget:
    return proto.script_box.children[-1]


def ask_and_check(
    proto: ui.Prototype,
    app: toga.App,
    box: toga.Widget,
    field: toga.Widget,
    answer: str,
) -> None:
    """Wait for `box` to ask, check it took the activity row's place, answer."""
    wait_for(app, lambda: box.parent is not None)
    assert last_row(proto) is box
    assert proto.script_activity.parent is None
    field.value = answer  # type: ignore[attr-defined]
    proto.script_runner.handle_ui_submit(field)


def test_input_swaps_with_the_activity_row(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (docs / "case.py").write_text("name = input('Name? ')\nprint('Hello', name)\n")
    proto.reload_menu(proto.script_list)
    tap(proto, "case", monkeypatch, app)
    ask_and_check(proto, app, proto.input_box, proto.input_text, "Ada")
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    assert last_row(proto) is proto.script_activity
    assert proto.input_box.parent is None


def test_getpass_then_input_keep_one_row(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One question after another: each in turn, then the activity back."""
    (docs / "case.py").write_text(
        "import getpass\npw = getpass.getpass('Secret: ')\n"
        "name = input('Name? ')\nprint(len(pw), name)\n"
    )
    proto.reload_menu(proto.script_list)
    tap(proto, "case", monkeypatch, app)
    ask_and_check(proto, app, proto.password_box, proto.password_text, "hunter2")
    ask_and_check(proto, app, proto.input_box, proto.input_text, "Ada")
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    assert proto.print_text.value.endswith("7 Ada\n")
    assert last_row(proto) is proto.script_activity
    rows = proto.script_box.children
    assert proto.input_box not in rows and proto.password_box not in rows


def test_both_boxes_at_once_leave_one_activity_row(proto: ui.Prototype) -> None:
    """Shown together (not usual), putting one away doesn't bring the row back."""
    proto.toggle_input(True)
    proto.toggle_password(True)
    proto.toggle_input(False)
    assert last_row(proto) is proto.password_box
    assert proto.script_activity.parent is None
    proto.toggle_password(False)
    assert last_row(proto) is proto.script_activity
    assert proto.script_box.children.count(proto.script_activity) == 1
