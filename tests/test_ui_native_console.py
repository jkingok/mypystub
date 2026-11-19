"""Native mode with the Experimental Console: typing goes to the subprocess."""

import sys
from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")
pytest.importorskip("toga_console")

import toga
from toga_console import Console

from mypystub import native, ui
from tests.support_ui import tap, wait_for


@pytest.fixture
def both(proto: ui.Prototype, config: Path, monkeypatch) -> ui.Prototype:
    """Native mode (with this Python as the venv's) and the console, both on."""
    monkeypatch.setattr(ui.Prototype, "native_mode", property(lambda self: True))
    monkeypatch.setattr(native, "ensure_venv", lambda cache: Path(sys.executable))
    proto.set_experimental_console(True)
    return proto


def start(proto: ui.Prototype, app: toga.App, docs: Path, source: str, mp) -> Console:
    (docs / "case.py").write_text(source)
    proto.reload_menu(proto.script_list)
    tap(proto, "case", mp, app)
    console = proto.script_output.children[0]
    assert isinstance(console, Console)
    return console


def ended(proto: ui.Prototype) -> bool:
    return proto.ended_run == proto.run_id > 0


def test_a_typed_line_reaches_the_process(
    both: ui.Prototype, app: toga.App, docs: Path, monkeypatch
) -> None:
    console = start(
        both, app, docs, "name = input('Name? ')\nprint('Hello', name)\n", monkeypatch
    )
    wait_for(app, lambda: "Name? " in console.value)
    assert not console.readonly
    assert both.input_box.parent is None  # the console, not the input field
    console.type("Sam\n")
    wait_for(app, lambda: ended(both))
    console.flush()
    assert "Name? Sam\nHello Sam\n" in console.value  # echoed once, by the console
    assert console.readonly


def test_ctrl_d_closes_the_process_stdin(
    both: ui.Prototype, app: toga.App, docs: Path, monkeypatch
) -> None:
    console = start(
        both,
        app,
        docs,
        "import sys\nprint('ready', flush=True)\n"
        "print(len(sys.stdin.read().splitlines()))\n",
        monkeypatch,
    )
    wait_for(app, lambda: "ready" in console.value)
    console.type("a\nb\n")
    console._impl.control("d")
    wait_for(app, lambda: ended(both))
    console.flush()
    assert "2\n" in console.value


@pytest.mark.skipif(sys.platform == "win32", reason="SIGINT is POSIX")
def test_ctrl_c_interrupts_the_process(
    both: ui.Prototype, app: toga.App, docs: Path, monkeypatch
) -> None:
    console = start(
        both,
        app,
        docs,
        "import time\nprint('ready', flush=True)\n"
        "try:\n    time.sleep(30)\nexcept KeyboardInterrupt:\n"
        "    print('interrupted')\n",
        monkeypatch,
    )
    wait_for(app, lambda: "ready" in console.value)
    console._impl.control("c")
    wait_for(app, lambda: ended(both))
    console.flush()
    assert "interrupted" in console.value
