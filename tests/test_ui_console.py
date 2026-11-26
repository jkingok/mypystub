"""Setup's Experimental Console: toga-console in the Script tab.

Runs real scripts through the launcher with the switch on, typing into the
console with toga-console's own dummy backend, as a user would.
"""

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("toga_dummy")
pytest.importorskip("toga_console")

import toga
from toga_console import Console

from mypystub import ui
from tests.support_ui import run_to_end, tap, wait_for


@pytest.fixture
def console_on(proto: ui.Prototype, config: Path) -> ui.Prototype:
    proto.set_experimental_console(True)
    return proto


def shown(proto: ui.Prototype) -> toga.Widget:
    return proto.script_output.children[0]


def test_off_by_default_and_the_usual_output_is_used(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch, config: Path
) -> None:
    assert proto.experimental_console is False
    run_to_end(proto, app, docs, "print('plain')\n", monkeypatch)
    assert shown(proto) is proto.print_text
    assert "plain" in proto.print_text.value


def test_output_and_errors_go_to_the_console(
    console_on: ui.Prototype, app: toga.App, docs: Path, monkeypatch
) -> None:
    proto = console_on
    run_to_end(
        proto,
        app,
        docs,
        "import sys\nprint('out')\nprint('err', file=sys.stderr)\n",
        monkeypatch,
    )
    console = shown(proto)
    assert isinstance(console, Console)
    console.flush()
    assert "out\n" in console.value and "err\n" in console.value
    assert proto.error_pane.style.display == "none"  # stderr is in the console


def test_input_is_typed_into_the_console(
    console_on: ui.Prototype, app: toga.App, docs: Path, monkeypatch
) -> None:
    proto = console_on
    (docs / "case.py").write_text("name = input('Name? ')\nprint('Hello', name)\n")
    proto.reload_menu(proto.script_list)
    tap(proto, "case", monkeypatch, app)
    console = shown(proto)
    assert isinstance(console, Console)
    wait_for(app, lambda: "Name? " in console.value)
    assert not console.readonly  # typeable for the whole run
    console.type("Sam\n")
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    console.flush()
    assert "Name? Sam\nHello Sam\n" in console.value
    assert console.readonly  # the run is over


def test_a_paste_answers_several_questions(
    console_on: ui.Prototype, app: toga.App, docs: Path, monkeypatch
) -> None:
    proto = console_on
    (docs / "case.py").write_text("a = input('A? ')\nb = input('B? ')\nprint(a + b)\n")
    proto.reload_menu(proto.script_list)
    tap(proto, "case", monkeypatch, app)
    console = shown(proto)
    wait_for(app, lambda: "A? " in console.value)
    console.type("1\n2\n")
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    console.flush()
    # Both lines echo when pasted; the second question is answered from stdin
    assert "A? 1\n2\nB? 12\n" in console.value


def test_typing_ahead_and_reading_stdin_directly(
    console_on: ui.Prototype, app: toga.App, docs: Path, monkeypatch
) -> None:
    """No hook: sys.stdin is the console, so any way of reading it works."""
    proto = console_on
    (docs / "case.py").write_text(
        "import sys\nprint('ready')\n"
        "print(sorted(line.strip() for line in sys.stdin))\n"
    )
    proto.reload_menu(proto.script_list)
    tap(proto, "case", monkeypatch, app)
    console = shown(proto)
    wait_for(app, lambda: "ready" in console.value)
    console.type("b\na\n")
    console._impl.control("d")  # Ctrl-D: end of input
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    console.flush()
    assert "['a', 'b']" in console.value


@pytest.mark.parametrize(
    ("key", "error"), [("d", "EOFError"), ("c", "KeyboardInterrupt")]
)
def test_ctrl_d_and_ctrl_c_end_input(
    console_on: ui.Prototype, app: toga.App, docs: Path, monkeypatch, key, error
) -> None:
    proto = console_on
    (docs / "case.py").write_text(
        "try:\n    input('? ')\nexcept BaseException as e:\n"
        "    print(type(e).__name__)\n"
    )
    proto.reload_menu(proto.script_list)
    tap(proto, "case", monkeypatch, app)
    console = shown(proto)
    wait_for(app, lambda: "? " in console.value)
    console._impl.control(key)
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    console.flush()
    assert error in console.value


def test_getpass_still_uses_the_password_field(
    console_on: ui.Prototype, app: toga.App, docs: Path, monkeypatch
) -> None:
    """The console would echo a password, so it isn't typed there."""
    proto = console_on
    (docs / "case.py").write_text(
        "import getpass\nsecret = getpass.getpass('PIN: ')\nprint(len(secret))\n"
    )
    proto.reload_menu(proto.script_list)
    tap(proto, "case", monkeypatch, app)
    wait_for(app, lambda: proto.password_box.parent is not None)
    proto.password_text.value = "1234"
    proto.password_text.on_confirm()  # type: ignore[misc]
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    console = shown(proto)
    console.flush()
    assert "4\n" in console.value and "1234" not in console.value


def test_switching_off_returns_to_the_usual_output_next_run(
    console_on: ui.Prototype, app: toga.App, docs: Path, monkeypatch
) -> None:
    proto = console_on
    run_to_end(proto, app, docs, "print(1)\n", monkeypatch)
    assert isinstance(shown(proto), Console)
    proto.set_experimental_console(False)
    run_to_end(proto, app, docs, "print(2)\n", monkeypatch)
    assert shown(proto) is proto.print_text and proto.script_runner.console is None


def test_run_end_puts_the_consoles_keyboard_away(proto: Any, monkeypatch: Any) -> None:
    """When a run ends, the console is read-only and its keyboard is closed."""
    closed: list[Any] = []
    proto.script_tab.console_widget = object()
    monkeypatch.setattr(proto, "close_keyboard", lambda widget: closed.append(widget))
    monkeypatch.setattr(proto.script_runner, "end_run", lambda: None)
    monkeypatch.setattr(proto, "end_script", lambda *a, **k: None)
    monkeypatch.setattr(proto, "remember", lambda: None)

    class Context:
        def close(self) -> None:
            pass

    proto.finish_run(Context(), None)
    assert closed == [proto.console_widget]
