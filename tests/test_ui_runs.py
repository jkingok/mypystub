"""UI tests for how a run ends, its output, and input() and getpass().

Skipped where toga_dummy isn't installed, such as on device.
"""

import asyncio
import os
from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import piplike, ui
from tests.support_ui import (
    run,
    run_to_end,
    tap,
    wait_for,
)

# ---------------------------------------------------------------------------
# How a run ends (#64): real scripts on a live loop
# ---------------------------------------------------------------------------


def test_silent_script_returns_to_list(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No output and no error: back to the list."""
    run_to_end(proto, app, docs, "x = 1 + 1\n", monkeypatch)
    assert proto.tabs.current_tab.text == "List"


def test_printing_script_stays_with_finished_status(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Output keeps the Script tab open, marked Finished."""
    run_to_end(proto, app, docs, "print(1 + 1)\n", monkeypatch)
    assert proto.tabs.current_tab.text == "Script"
    assert proto.print_text.value == "2\n"
    assert proto.script_activity.text.text == "Finished"


def test_launcher_output_during_a_run_does_not_count(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Launcher prints (here, its folder scan) don't keep the Script tab open."""
    source = (
        "from pathlib import Path\n"
        "from mypystub import scan\n"
        "scan.scan_all_prototypes(Path('.'))  # prints 'Scanning...'\n"
    )
    run_to_end(proto, app, docs, source, monkeypatch)
    assert proto.print_text.value == ""
    assert proto.tabs.current_tab.text == "List"


def test_main_thread_callback_output_counts(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cause 2: output from a callback scheduled on the loop is shown and counted."""
    source = "import toga\ntoga.App.app.loop.call_soon_threadsafe(print, 'later')\n"
    run_to_end(proto, app, docs, source, monkeypatch)
    assert proto.print_text.value == "later\n"
    assert proto.tabs.current_tab.text == "Script"


def test_error_without_output_shows_dialog_over_script_then_list(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dialog appears over the Script tab, then the list returns."""
    run_to_end(proto, app, docs, "raise ValueError('boom')\n", monkeypatch)
    assert proto.dialogs == [  # type: ignore[attr-defined]
        ("Script Failure", "Script failed with: boom", "Script", "Failed")
    ]
    assert proto.tabs.current_tab.text == "List"


def test_takeover_ends_after_its_pop_and_extra_pops_are_ignored(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cases A and E: tabs wait for the hand-back; a double Back changes nothing."""
    source = (
        "import toga\n"
        "app = toga.App.app\n"
        "def push():\n"
        "    mw = app.main_window\n"
        "    mw.content_stack.append((mw.title, mw.content))\n"
        "    mw.content = toga.Box()\n"
        "app.loop.call_soon_threadsafe(push)\n"
    )
    (docs / "case.py").write_text(source)
    proto.reload_menu(proto.script_list)
    tap(proto, "case", monkeypatch, app)
    stack = proto.content_stack()
    wait_for(app, lambda: len(stack) == 1)
    run(app, asyncio.sleep(0.05))
    assert proto.ended_run != proto.run_id  # still taken over

    _title, content = stack.pop()  # Back
    app.main_window.content = content
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    assert proto.tabs.current_tab.text == "List"

    assert stack.pop() == (app.main_window.title, app.main_window.content)  # 2nd Back
    assert app.main_window.content is content


def test_takeover_example_hands_back_on_back(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bundled takeover example ends its run when its Back button is pressed."""
    example = (
        Path(ui.__file__).parent
        / "resources"
        / "examples"
        / "takeover"
        / "back_button.py"
    )
    (docs / "case.py").write_text(example.read_text(encoding="utf-8"))
    proto.reload_menu(proto.script_list)
    launcher = app.main_window.content
    tap(proto, "case", monkeypatch, app)
    stack = proto.content_stack()
    wait_for(app, lambda: len(stack) == 1)
    assert app.main_window.title == "Takeover"
    assert proto.ended_run != proto.run_id

    takeover = app.main_window.content
    back = next(w for w in takeover.children if isinstance(w, toga.Button))
    back._impl.simulate_press()
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    assert app.main_window.content is launcher
    assert proto.tabs.current_tab.text == "Script"  # it printed a line
    assert "Took over the screen" in proto.print_text.value

    back._impl.simulate_press()  # a double tap changes nothing
    run(app, asyncio.sleep(0.05))
    assert app.main_window.content is launcher


def test_stale_run_end_is_ignored(proto: ui.Prototype) -> None:
    """Case G: an old run finishing late doesn't touch the current run's UI."""
    from mypystub import runner

    proto.run_id = 2
    proto.tabs.current_tab = "Script"
    context = runner.RunContext(
        runner.target_for(Path(__file__), Path(__file__).parent)
    )
    proto.finish_run(context, None, run_id=1)
    assert proto.tabs.current_tab.text == "Script"
    assert proto.ended_run != 1


def test_installs_use_configured_and_script_aliases(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """launcher.toml aliases and the script's own are passed to the installer."""
    (docs / "aliased.py").write_text(
        '"""Aliased."""\n'
        "# /// script\n"
        '# dependencies = ["fast"]\n'
        "# [tool.stub_launcher.aliases]\n"
        '# fast = { kind = "substitute", target = "fast-pure" }\n'
        "# ///\n"
    )
    configured = {"slow": piplike.Alias("substitute", "slow-pure")}
    monkeypatch.setattr(proto, "configured_aliases", lambda: configured)
    seen: list[object] = []

    async def install(*args: object, **kwargs: object) -> None:
        seen.append(kwargs.get("aliases"))
        raise piplike.DependencyError("stop")

    monkeypatch.setattr(piplike, "resolve_and_install_async", install)
    proto.reload_menu(proto.script_list)
    tap(proto, "aliased", monkeypatch, app)
    assert seen == [
        {
            "slow": piplike.Alias("substitute", "slow-pure"),
            "fast": piplike.Alias("substitute", "fast-pure"),
        }
    ]


def test_nested_takeover_example_ends_back_at_the_launcher(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two levels deep: the run ends only when both screens are handed back."""
    example = (
        Path(ui.__file__).parent
        / "resources"
        / "examples"
        / "takeover"
        / "nested_takeover.py"
    )
    (docs / "case.py").write_text(example.read_text(encoding="utf-8"))
    proto.reload_menu(proto.script_list)
    launcher = app.main_window.content
    tap(proto, "case", monkeypatch, app)
    stack = proto.content_stack()
    wait_for(app, lambda: len(stack) == 1)

    def press(label: str) -> None:
        content = app.main_window.content
        button = next(
            w
            for w in content.children
            if isinstance(w, toga.Button) and w.text == label
        )
        button._impl.simulate_press()

    press("Deeper")
    wait_for(app, lambda: len(stack) == 2)
    assert app.main_window.title == "Level 2"

    press("Back")
    wait_for(app, lambda: len(stack) == 1)
    run(app, asyncio.sleep(0.05))
    assert proto.ended_run != proto.run_id  # still one level in

    press("Back")
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    assert app.main_window.content is launcher


# ---------------------------------------------------------------------------
# A run's stdout and stderr (#119)
# ---------------------------------------------------------------------------


def test_stderr_pane_appears_only_when_written_to(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stderr goes to its own pane, shown on the first write; stdout stays put."""
    assert proto.error_pane.style.display == "none"
    source = (
        "import sys\nsys.stdout.write('out\\n')\nprint('warned', file=sys.stderr)\n"
    )
    run_to_end(proto, app, docs, source, monkeypatch)
    assert proto.print_text.value == "out\n"
    assert proto.error_text.value == "warned\n"
    assert proto.error_pane.style.display == "pack"
    assert proto.error_text.style.color is not None  # the warning colour


def test_hide_lasts_until_the_next_write(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hide hides the pane; more stderr shows it again; a new run starts hidden."""
    run_to_end(proto, app, docs, "import sys\nsys.stderr.write('a\\n')\n", monkeypatch)
    proto.hide_errors()
    assert proto.error_pane.style.display == "none"
    proto.show_error_output("b\n")
    assert proto.error_pane.style.display == "pack"
    assert proto.error_text.value == "a\nb\n"

    run_to_end(proto, app, docs, "print('quiet')\n", monkeypatch)
    assert proto.error_text.value == ""
    assert proto.error_pane.style.display == "none"


def test_script_output_container_is_orientation_aware(proto: ui.Prototype) -> None:
    """Output and errors share the Script tab: stacked in portrait, side by side
    in landscape."""
    from mypystub.widgets import OrientationBox

    assert isinstance(proto.script_output, OrientationBox)
    assert proto.script_output.children == [proto.script_scroll, proto.error_pane]


def test_streams_are_restored_after_a_run(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After the run, sys.stdout and sys.stderr are the app's again."""
    import sys

    stdout, stderr = sys.stdout, sys.stderr
    run_to_end(proto, app, docs, "print('x')\n", monkeypatch)
    assert (sys.stdout, sys.stderr) == (stdout, stderr)


# input() is echoed; getpass() asks without showing the password (#121)
# ---------------------------------------------------------------------------


def answer_when_asked(
    proto: ui.Prototype, app: toga.App, box: toga.Widget, field: toga.Widget, text: str
) -> None:
    """Wait for the script to ask with `box`, then type `text` and press Return."""
    wait_for(app, lambda: box.parent is not None)
    field.value = text  # type: ignore[attr-defined]
    proto.script_runner.handle_ui_submit(field)


def test_input_is_echoed_in_the_script_tab(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The prompt and answer appear in the output, then the script's own print."""
    (docs / "case.py").write_text("name = input('Name? ')\nprint('Hello', name)\n")
    proto.reload_menu(proto.script_list)
    tap(proto, "case", monkeypatch, app)
    answer_when_asked(proto, app, proto.input_box, proto.input_text, "Ada")
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    assert proto.print_text.value == "Name? Ada\nHello Ada\n"
    assert proto.input_box.parent is None  # the field is put away again


def test_getpass_uses_the_password_field_and_hides_the_answer(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """getpass shows only its prompt, in the password field's box."""
    (docs / "case.py").write_text(
        "import getpass\npw = getpass.getpass('Secret: ')\nprint(len(pw))\n"
    )
    proto.reload_menu(proto.script_list)
    tap(proto, "case", monkeypatch, app)
    answer_when_asked(proto, app, proto.password_box, proto.password_text, "hunter2")
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    assert proto.print_text.value == "Secret: \n7\n"
    assert "hunter2" not in proto.print_text.value
    assert proto.password_box.parent is None and proto.input_box.parent is None
    assert proto.password_text.value == ""
