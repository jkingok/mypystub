"""The Script tab's status row says how a run ended, with ✅ or ❌, and keeps it.

The status used to go back to "Finished" once a failure's dialog was
dismissed, and sys.exit(3) read the same as a clean end.
"""

from pathlib import Path

import pytest
import toga

from mypystub import runner, ui
from mypystub.ui_run import FINISHED, run_status
from tests.support_ui import tap, wait_for


def test_clean_ends_are_finished() -> None:
    assert run_status(None) == FINISHED == "✅ Finished"
    assert run_status(SystemExit()) == FINISHED
    assert run_status(SystemExit(0)) == FINISHED


def test_exit_status_and_message() -> None:
    assert run_status(SystemExit(3)) == "❌ Exited with status 3"
    assert run_status(SystemExit("bad input")) == "❌ Exited: bad input"


def test_exceptions_name_their_type() -> None:
    assert run_status(ValueError("boom")) == "❌ Failed: ValueError"
    assert run_status(KeyboardInterrupt()) == "❌ Failed: KeyboardInterrupt"


def test_scripts_that_cant_run() -> None:
    assert run_status(runner.NotRunnable("no main")) == "⚠️ Couldn't run"


def run_source(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    source: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (docs / "case.py").write_text(source)
    proto.reload_menu(proto.script_list)
    tap(proto, "case", monkeypatch, app)
    wait_for(app, lambda: proto.ended_run == proto.run_id)


def test_a_failure_keeps_its_status_after_the_dialog(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_source(
        proto, app, docs, "print('working')\nraise ValueError('boom')\n", monkeypatch
    )
    assert proto.script_activity.text.text == "❌ Failed: ValueError"
    assert proto.tabs.current_tab.text == "Script"


def test_an_exit_status_is_shown(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_source(proto, app, docs, "import sys\nprint('x')\nsys.exit(3)\n", monkeypatch)
    assert proto.script_activity.text.text == "❌ Exited with status 3"


def test_a_clean_exit_is_finished(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_source(proto, app, docs, "import sys\nprint('x')\nsys.exit(0)\n", monkeypatch)
    assert proto.script_activity.text.text == "✅ Finished"


def test_a_silent_run_still_leaves_its_status(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Back on the list, the Script tab still says how the run went."""
    run_source(proto, app, docs, "raise ValueError('quiet')\n", monkeypatch)
    assert proto.tabs.current_tab.text == "List"
    assert proto.script_activity.text.text == "❌ Failed: ValueError"
