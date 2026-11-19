"""Native mode in the launcher: a script runs in a real subprocess (#280).

The managed venv is replaced by the Python running the tests, so nothing is
installed; everything else (the subprocess, its output and stdin) is real.
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")

import toga

from mypystub import native, ui
from mypystub.run_status import STOPPED
from tests.support_ui import run, tap, wait_for


@pytest.fixture
def native_proto(proto: ui.Prototype, monkeypatch: pytest.MonkeyPatch) -> ui.Prototype:
    """The launcher with Native mode on, using this Python as the venv's."""
    monkeypatch.setattr(ui.Prototype, "native_mode", property(lambda self: True))
    monkeypatch.setattr(native, "ensure_venv", lambda cache: Path(sys.executable))
    return proto


def run_script(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    source: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (docs / "case.py").write_text(source)
    proto.reload_menu(proto.script_list)
    tap(proto, "case", monkeypatch, app)


def test_output_and_errors_reach_the_script_tab(
    native_proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch
) -> None:
    run_script(
        native_proto,
        app,
        docs,
        "import os, sys\nprint('pid', os.getpid() != int(sys.argv[0] == ''))\n"
        "print('to stderr', file=sys.stderr)\n",
        monkeypatch,
    )
    wait_for(app, lambda: native_proto.ended_run == native_proto.run_id > 0)
    assert "pid True" in native_proto.print_text.value
    assert "to stderr" in native_proto.error_text.value
    assert native_proto.dialogs == []  # type: ignore[attr-defined]


def test_it_runs_in_another_process(
    native_proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch
) -> None:
    import os

    run_script(native_proto, app, docs, "import os\nprint(os.getpid())\n", monkeypatch)
    wait_for(app, lambda: native_proto.ended_run == native_proto.run_id > 0)
    assert native_proto.print_text.value.strip() != str(os.getpid())


def test_input_goes_to_stdin_and_is_echoed(
    native_proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch
) -> None:
    run_script(
        native_proto,
        app,
        docs,
        "name = input('Name? ')\nprint('Hello', name)\n",
        monkeypatch,
    )
    wait_for(app, lambda: "Name? " in native_proto.print_text.value)
    assert native_proto.input_box.parent is not None  # the field is offered
    native_proto.input_text.value = "Sam"
    native_proto.input_text.on_confirm()  # type: ignore[misc]  (Toga passes the widget)
    wait_for(app, lambda: native_proto.ended_run == native_proto.run_id > 0)
    assert "Name? Sam\nHello Sam" in native_proto.print_text.value
    assert native_proto.input_box.parent is None  # put away again


def test_a_failing_script_reports_its_status(
    native_proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch
) -> None:
    run_script(native_proto, app, docs, "raise SystemExit(4)\n", monkeypatch)
    wait_for(app, lambda: bool(native_proto.dialogs))  # type: ignore[attr-defined]
    title, text, *_ = native_proto.dialogs[0]  # type: ignore[attr-defined]
    assert title == "Script Failure" and "status 4" in text


def test_a_failed_install_is_a_dependency_error(
    native_proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        native, "pip_command", lambda python, reqs: [sys.executable, "-c", "exit(1)"]
    )
    run_script(
        native_proto,
        app,
        docs,
        "# /// script\n# dependencies = ['nothing-real']\n# ///\nprint('ran')\n",
        monkeypatch,
    )
    wait_for(app, lambda: bool(native_proto.dialogs))  # type: ignore[attr-defined]
    title, text, *_ = native_proto.dialogs[0]  # type: ignore[attr-defined]
    assert title == "Dependency Error" and "nothing-real" in text
    assert "ran" not in native_proto.print_text.value


def test_the_switch_is_saved(proto: ui.Prototype, monkeypatch) -> None:
    monkeypatch.undo()  # the real property, not the fixture's stand-in
    proto.set_native_mode(False)
    assert proto.settings.get_flag(native.SETTING, True) is False
    proto.set_native_mode(True)
    assert proto.settings.get_flag(native.SETTING, False) is True


def test_stop_ends_a_running_script(
    native_proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch
) -> None:
    """Stop shows while it runs; pressing it ends the process, with no error."""
    run_script(
        native_proto,
        app,
        docs,
        "import time\nprint('started', flush=True)\ntime.sleep(60)\n",
        monkeypatch,
    )
    wait_for(app, lambda: "started" in native_proto.print_text.value)
    assert native_proto.stop_button.style.visibility == "visible"
    run(app, native_proto.handle_stop())
    wait_for(app, lambda: native_proto.ended_run == native_proto.run_id > 0)
    assert native_proto.stop_button.style.visibility == "hidden"
    assert native_proto.script_activity.text.text == STOPPED
    assert native_proto.dialogs == []  # type: ignore[attr-defined]


def test_stop_kills_a_process_that_ignores_terminate(
    native_proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch
) -> None:
    from mypystub import ui_native

    monkeypatch.setattr(ui_native, "STOP_GRACE", 0.2)
    run_script(
        native_proto,
        app,
        docs,
        "import signal, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "print('started', flush=True)\ntime.sleep(60)\n",
        monkeypatch,
    )
    wait_for(app, lambda: "started" in native_proto.print_text.value)
    run(app, native_proto.handle_stop())
    wait_for(app, lambda: native_proto.ended_run == native_proto.run_id > 0)
    assert native_proto.script_activity.text.text == STOPPED


def test_wipe_also_removes_the_venv(
    proto: ui.Prototype, app: toga.App, monkeypatch
) -> None:
    venv = Path(proto.cache_path) / native.VENV_FOLDER
    (venv / "bin").mkdir(parents=True, exist_ok=True)
    (venv / "bin" / "python").write_text("")

    async def yes(*args: object, **kwargs: object) -> bool:
        return True

    monkeypatch.setattr(proto, "confirm", yes)
    run(app, proto.handle_wipe_cache(proto.stop_button))
    assert not venv.exists()


def test_the_status_row_keeps_the_exit_status(
    native_proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch
) -> None:
    """As for an in-process run (#293), after the dialog is dismissed."""
    run_script(native_proto, app, docs, "raise SystemExit(4)\n", monkeypatch)
    wait_for(app, lambda: native_proto.ended_run == native_proto.run_id > 0)
    assert native_proto.script_activity.text.text == "❌ Exited with status 4"


def test_a_clean_exit_is_finished(
    native_proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch
) -> None:
    from mypystub.run_status import FINISHED

    run_script(native_proto, app, docs, "print('ok')\n", monkeypatch)
    wait_for(app, lambda: native_proto.ended_run == native_proto.run_id > 0)
    assert native_proto.script_activity.text.text == FINISHED
