"""Script output capture for the Script tab (mypystub.hooks, #64)."""

import builtins
import io
import sys
from collections.abc import Callable
from types import SimpleNamespace

import pytest

from mypystub.hooks import ScriptRunner


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
