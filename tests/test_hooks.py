"""Script output capture for the Script tab (mypystub.hooks, #64)."""

import builtins
import io
import sys
from collections.abc import Callable
from types import SimpleNamespace

import pytest

from mypystub.hooks import (
    RunStream,
    ScriptRunner,
    raised_by_prototype,
    report_exception,
)


class FakeLoop:
    """Records how callbacks were queued, and runs them on demand."""

    def __init__(self) -> None:
        self.ready: list[Callable[[], object]] = []
        self.unsafe_calls = 0

    def call_soon(self, callback: Callable[..., object], *args: object) -> None:
        """Not thread-safe: counted, so tests can insist it isn't used."""
        self.unsafe_calls += 1
        self.ready.append(lambda: callback(*args))

    def call_soon_threadsafe(
        self, callback: Callable[..., object], *args: object
    ) -> None:
        """Queue a callback the way script threads must."""
        self.ready.append(lambda: callback(*args))

    def run_ready(self) -> None:
        """Run everything queued so far."""
        while self.ready:
            self.ready.pop(0)()


@pytest.fixture
def log() -> io.StringIO:
    """The app's log: sys.stdout and sys.stderr both write here, as on device."""
    return io.StringIO()


@pytest.fixture
def runner(log: io.StringIO, monkeypatch: pytest.MonkeyPatch) -> ScriptRunner:
    """A ScriptRunner wired to fake widgets and a fake loop."""
    loop = FakeLoop()
    app = SimpleNamespace(loop=loop)
    widget = SimpleNamespace(value="", text="", on_confirm=None, focus=lambda: None)
    errors: list[str] = []
    runner = ScriptRunner(
        app,  # type: ignore[arg-type]
        widget,  # type: ignore[arg-type]
        widget,  # type: ignore[arg-type]
        SimpleNamespace(value=""),  # type: ignore[arg-type]
        lambda on: None,
        lambda on: None,
        on_error_output=errors.append,
    )
    runner.errors = errors  # type: ignore[attr-defined]
    real_begin = runner.begin_run

    def begin_run() -> None:
        # pytest swaps sys.stdout in for each test phase, so point the streams
        # at the log only now, when the test body starts the run
        monkeypatch.setattr(sys, "stdout", log)
        monkeypatch.setattr(sys, "stderr", log)
        real_begin()

    runner.begin_run = begin_run  # type: ignore[method-assign]
    yield runner
    runner.end_run()  # never leave the streams swapped


def print_from(module_name: str, text: str) -> None:
    """Call print() as if from code in `module_name`."""
    # Test-only: a constant call, run with that module's __name__
    exec(f"print({text!r})", {"__name__": module_name})  # noqa: S102


def test_script_thread_output_is_queued_threadsafely(runner: ScriptRunner) -> None:
    """From the script thread, output is queued with call_soon_threadsafe."""
    import threading

    runner.begin_run()
    worker = threading.Thread(target=print_from, args=("__main__", "hello"))
    worker.start()
    worker.join()
    loop = runner.app.loop
    assert loop.unsafe_calls == 0
    assert runner.print_field.value == ""  # queued, not yet on screen
    loop.run_ready()
    assert runner.print_field.value == "hello\n"
    assert runner.printed


def test_main_thread_output_is_counted_immediately(runner: ScriptRunner) -> None:
    """A script callback printing on the loop is counted before any later check."""
    runner.begin_run()
    print_from("__main__", "from a callback")
    assert runner.printed
    assert runner.print_field.value == "from a callback\n"


def test_launcher_output_is_not_counted(runner: ScriptRunner) -> None:
    """The launcher's own prints during a run go to the log, not the Script tab."""
    runner.begin_run()
    print_from("mypystub.ui", "Scanning for launcher prototypes")
    print_from("mypystub.piplike", "[Progress] Checking dependencies")
    runner.app.loop.run_ready()
    assert runner.print_field.value == ""
    assert not runner.printed


def test_hooks_last_for_the_whole_run(runner: ScriptRunner, log: io.StringIO) -> None:
    """The streams and input stay hooked until the run ends."""
    original_input = builtins.input
    runner.begin_run()
    assert sys.stdout is not log and sys.stderr is not log
    assert builtins.input is not original_input
    runner.end_run()
    assert sys.stdout is log and sys.stderr is log
    assert builtins.input is original_input


def run_as(module_name: str, code: str) -> None:
    """Run `code` as if it were in `module_name`."""
    exec(code, {"__name__": module_name})  # noqa: S102 (test-only constant code)


def test_everything_is_still_logged_unmarked(
    runner: ScriptRunner, log: io.StringIO
) -> None:
    """The log gets every write as it was, the launcher's included (tee)."""
    runner.begin_run()
    print_from("__main__", "shown")
    print_from("mypystub.ui", "launcher only")
    run_as("__main__", "import sys\nsys.stderr.write('warned\\n')")
    assert log.getvalue() == "shown\nlauncher only\nwarned\n"


def test_stdout_writes_are_shown(runner: ScriptRunner) -> None:
    """sys.stdout.write reaches the Script tab, not just print()."""
    runner.begin_run()
    run_as("__main__", "import sys\nsys.stdout.write('direct\\n')")
    assert runner.print_field.value == "direct\n"
    assert runner.errors == []  # type: ignore[attr-defined]


def test_stderr_goes_to_the_error_output(runner: ScriptRunner) -> None:
    """stderr is shown separately, and counts as output."""
    runner.begin_run()
    run_as("__main__", "import sys\nprint('oops', file=sys.stderr)")
    assert runner.errors == ["oops", "\n"]  # type: ignore[attr-defined]
    assert runner.print_field.value == ""
    assert runner.printed


def test_standard_library_writes_count_for_the_prototype(
    runner: ScriptRunner,
) -> None:
    """A traceback printed by the traceback module, for the script, is shown."""
    runner.begin_run()
    run_as("__main__", "import traceback\ntraceback.print_stack(limit=1)")
    assert "".join(runner.errors).startswith("  File")  # type: ignore[attr-defined]


def test_launcher_and_toga_stderr_are_log_only(
    runner: ScriptRunner, log: io.StringIO
) -> None:
    """Writes by the launcher or Toga on the loop aren't the prototype's."""
    runner.begin_run()
    run_as("mypystub.ui", "import sys\nsys.stderr.write('launcher\\n')")
    run_as("toga.app", "import sys\nsys.stderr.write('toga\\n')")
    run_as("toga_iOS.window", "import sys\nsys.stderr.write('backend\\n')")
    assert runner.errors == []  # type: ignore[attr-defined]
    assert not runner.printed
    assert "launcher\ntoga\nbackend\n" in log.getvalue()


def test_ansi_codes_are_stripped_on_screen_but_logged(
    runner: ScriptRunner, log: io.StringIO
) -> None:
    """The Script tab shows plain text; the log keeps what was written."""
    runner.begin_run()
    print_from("__main__", "\x1b[31mred\x1b[0m")
    assert runner.print_field.value == "red\n"
    assert "\x1b[31mred" in log.getvalue()


def test_begin_run_resets_printed(runner: ScriptRunner) -> None:
    """Each run starts with no output counted."""
    runner.begin_run()
    print_from("__main__", "first run")
    runner.app.loop.run_ready()
    runner.end_run()
    runner.begin_run()
    assert not runner.printed


def test_interactive_console_output_reaches_both_panes(runner: ScriptRunner) -> None:
    """code's console: results (displayhook) to stdout, tracebacks to stderr."""
    runner.begin_run()
    run_as(
        "__main__",
        "import code\n"
        "console = code.InteractiveInterpreter({'__name__': '__console__'})\n"
        "console.runsource('6 * 7')\n"
        "console.runsource('1 / 0')\n",
    )
    assert runner.print_field.value == "42\n"
    assert "ZeroDivisionError" in "".join(runner.errors)  # type: ignore[attr-defined]


def caught_in_launcher(prototype_code: str) -> BaseException:
    """An exception from `prototype_code` (run as __main__), caught by the launcher.

    The traceback starts in a launcher frame, as one from Rubicon's run loop or
    a thread does, and passes through the prototype's code if it raised there.
    """
    script: dict[str, object] = {"__name__": "__main__"}
    exec(f"def work():\n    {prototype_code}\n", script)  # noqa: S102
    launcher: dict[str, object] = {"__name__": "mypystub.app", "work": script["work"]}
    # Test-only: constant code, run with the launcher's __name__
    exec(  # noqa: S102
        "try:\n    work()\nexcept Exception as e:\n    caught = e\n", launcher
    )
    caught = launcher["caught"]
    assert isinstance(caught, BaseException)
    return caught


def test_prototype_errors_caught_by_the_launcher_are_shown(
    runner: ScriptRunner, log: io.StringIO
) -> None:
    """A main-thread callback's error reaches the error pane, not just the log."""
    runner.begin_run()
    exc = caught_in_launcher("raise ValueError('not my values')")
    report_exception(type(exc), exc, exc.__traceback__)
    shown = "".join(runner.errors)  # type: ignore[attr-defined]
    assert shown.startswith("Traceback (most recent call last):")
    assert "ValueError: not my values" in shown
    assert "ValueError: not my values" in log.getvalue()


def test_launcher_errors_are_logged_only(
    runner: ScriptRunner, log: io.StringIO
) -> None:
    """An error in the launcher's own code isn't shown as the prototype's."""
    runner.begin_run()
    launcher: dict[str, object] = {"__name__": "mypystub.ui"}
    # Test-only: constant code, run with the launcher's __name__
    exec(  # noqa: S102
        "try:\n    1 / 0\nexcept Exception as e:\n    caught = e\n", launcher
    )
    exc = launcher["caught"]
    assert isinstance(exc, BaseException)
    assert not raised_by_prototype(exc.__traceback__)
    report_exception(type(exc), exc, exc.__traceback__)
    assert runner.errors == []  # type: ignore[attr-defined]
    assert "ZeroDivisionError" in log.getvalue()


def test_errors_outside_a_run_go_to_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no run, the traceback is simply written to sys.stderr."""
    err = io.StringIO()
    monkeypatch.setattr(sys, "stderr", err)
    exc = caught_in_launcher("raise KeyError('k')")
    report_exception(type(exc), exc, exc.__traceback__)
    assert "KeyError: 'k'" in err.getvalue()


def test_the_logs_other_attributes_pass_through(
    runner: ScriptRunner, log: io.StringIO
) -> None:
    """The Logs tab finds the log file's path during a run, too."""
    log.path = "app_runtime.log"  # type: ignore[attr-defined]
    runner.begin_run()
    assert isinstance(sys.stdout, RunStream)
    assert sys.stdout.path == "app_runtime.log"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# input() and getpass() (#121)
# ---------------------------------------------------------------------------


class Fields:
    """Fake input widgets and what the launcher was asked to show."""

    def __init__(self) -> None:
        self.label = SimpleNamespace(text="")
        self.field = SimpleNamespace(value="", on_confirm=None, focus=lambda: None)
        self.password_label = SimpleNamespace(text="")
        self.password_field = SimpleNamespace(
            value="", on_confirm=None, focus=lambda: None
        )
        self.shown: list[str] = []


@pytest.fixture
def io_runner(log: io.StringIO, monkeypatch: pytest.MonkeyPatch) -> ScriptRunner:
    """A runner with separate text and password fields, and a log."""
    fields = Fields()
    loop = FakeLoop()
    runner = ScriptRunner(
        SimpleNamespace(loop=loop),  # type: ignore[arg-type]
        fields.label,  # type: ignore[arg-type]
        fields.field,  # type: ignore[arg-type]
        SimpleNamespace(value=""),  # type: ignore[arg-type]
        lambda on: fields.shown.append("text" if on else "-text"),
        lambda on: None,
        password_label=fields.password_label,  # type: ignore[arg-type]
        password_field=fields.password_field,  # type: ignore[arg-type]
        toggle_password=lambda on: fields.shown.append(
            "password" if on else "-password"
        ),
    )
    runner.fields = fields  # type: ignore[attr-defined]

    def start() -> None:
        # pytest swaps sys.stdout in for each test phase, so point the streams
        # at the log only now, when the test body starts the run
        monkeypatch.setattr(sys, "stdout", log)
        monkeypatch.setattr(sys, "stderr", log)
        runner.begin_run()

    runner.start = start  # type: ignore[attr-defined]
    yield runner
    runner.end_run()


def ask_from_script(
    runner: ScriptRunner, call: Callable[[], str], answer: str, secret: bool = False
) -> str:
    """Run `call` on a script thread, answer it from the 'main thread'."""
    import threading

    fields = runner.fields  # type: ignore[attr-defined]
    result: list[str] = []
    worker = threading.Thread(target=lambda: result.append(call()))
    worker.start()
    loop = runner.app.loop
    for _ in range(500):  # wait for the prompt to be queued
        if loop.ready:
            break
        threading.Event().wait(0.01)
    loop.run_ready()  # shows the field
    field = fields.password_field if secret else fields.field
    field.value = answer
    runner.handle_ui_submit(field)
    worker.join(timeout=5)
    return result[0]


def test_input_returns_the_answer_and_echoes_it(
    io_runner: ScriptRunner, log: io.StringIO
) -> None:
    """The prompt and the typed answer land in the output and the log, once."""
    io_runner.start()  # type: ignore[attr-defined]
    answer = ask_from_script(io_runner, lambda: input("Name? "), "Ada")
    assert answer == "Ada"
    assert io_runner.print_field.value == "Name? Ada\n"
    assert log.getvalue() == "Name? Ada\n"
    assert io_runner.printed


def test_echo_keeps_order_with_surrounding_output(
    io_runner: ScriptRunner, log: io.StringIO
) -> None:
    """Output before and after the question stays in order around the echo."""
    io_runner.start()  # type: ignore[attr-defined]
    print_from("__main__", "before")
    ask_from_script(io_runner, lambda: input(">>> "), "x * 7")
    print_from("__main__", "42")
    io_runner.app.loop.run_ready()
    assert io_runner.print_field.value == "before\n>>> x * 7\n42\n"
    assert log.getvalue() == "before\n>>> x * 7\n42\n"


def test_input_without_a_prompt_echoes_the_answer(io_runner: ScriptRunner) -> None:
    """A bare input() still shows what was typed."""
    io_runner.start()  # type: ignore[attr-defined]
    ask_from_script(io_runner, lambda: input(), "hi")
    assert io_runner.print_field.value == "hi\n"


def test_getpass_uses_the_password_field_and_hides_the_value(
    io_runner: ScriptRunner, log: io.StringIO
) -> None:
    """getpass shows the prompt and a newline, never the password."""
    io_runner.start()  # type: ignore[attr-defined]
    import getpass

    answer = ask_from_script(
        io_runner, lambda: getpass.getpass("Password: "), "s3cret", secret=True
    )
    assert answer == "s3cret"
    assert io_runner.print_field.value == "Password: \n"
    assert "s3cret" not in log.getvalue()
    fields = io_runner.fields  # type: ignore[attr-defined]
    assert fields.shown == ["password", "-password"]  # not the text field
    assert fields.password_field.value == ""  # cleared after submit
    assert fields.password_label.text == "Password: "


def test_getpass_default_prompt_and_stream_argument(io_runner: ScriptRunner) -> None:
    """getpass() keeps its signature: default prompt, and a stream that's ignored."""
    io_runner.start()  # type: ignore[attr-defined]
    import getpass

    ask_from_script(
        io_runner,
        lambda: getpass.getpass(stream=io.StringIO()),
        "pw",
        secret=True,
    )
    assert io_runner.fields.password_label.text == "Password: "  # type: ignore[attr-defined]


def test_hooks_are_restored_after_the_run() -> None:
    """input and getpass are the originals again once the run ends."""
    import getpass

    original_input, original_getpass = builtins.input, getpass.getpass
    runner = ScriptRunner(
        SimpleNamespace(loop=FakeLoop()),  # type: ignore[arg-type]
        SimpleNamespace(text=""),  # type: ignore[arg-type]
        SimpleNamespace(value="", on_confirm=None),  # type: ignore[arg-type]
        SimpleNamespace(value=""),  # type: ignore[arg-type]
        lambda on: None,
        lambda on: None,
    )
    runner.begin_run()
    assert builtins.input is not original_input
    assert getpass.getpass is not original_getpass
    runner.end_run()
    assert builtins.input is original_input
    assert getpass.getpass is original_getpass
