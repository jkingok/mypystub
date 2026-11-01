"""Script output capture for the Script tab (mypystub.hooks, #64)."""

import builtins
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
def runner(monkeypatch: pytest.MonkeyPatch) -> ScriptRunner:
    """A ScriptRunner wired to fake widgets and a fake loop."""
    loop = FakeLoop()
    app = SimpleNamespace(loop=loop)
    widget = SimpleNamespace(value="", text="", on_confirm=None, focus=lambda: None)
    runner = ScriptRunner(
        app,  # type: ignore[arg-type]
        widget,  # type: ignore[arg-type]
        widget,  # type: ignore[arg-type]
        SimpleNamespace(value=""),  # type: ignore[arg-type]
        lambda on: None,
        lambda on: None,
    )
    yield runner
    runner.end_run()  # never leave print hooked


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


def test_hooks_last_for_the_whole_run(runner: ScriptRunner) -> None:
    """print stays hooked until the run ends, so main-thread callbacks count."""
    original = builtins.print
    runner.begin_run()
    assert builtins.print is not original
    runner.end_run()
    assert builtins.print is original


def test_begin_run_resets_printed(runner: ScriptRunner) -> None:
    """Each run starts with no output counted."""
    runner.begin_run()
    print_from("__main__", "first run")
    runner.app.loop.run_ready()
    runner.end_run()
    runner.begin_run()
    assert not runner.printed
