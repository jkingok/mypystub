"""
Module of functions for hooking/monkey-patching APIs for our purposes.

During a run, ``input`` reads from the Script tab, and ``sys.stdout`` and
``sys.stderr`` are teed: everything still goes to the app's log, unchanged,
and what the prototype writes is also shown in the Script tab, with stderr
shown separately (#119).
"""

import builtins
import io
import re
import sys
import threading
import traceback
from collections.abc import Callable
from types import TracebackType
from typing import Any

import toga

# Regex pattern to match standard ANSI escape sequences (like \x1b[31m)
ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def clean_ansi(text: str) -> str:
    """Removes ANSI color and formatting codes from a string."""
    return ANSI_ESCAPE_RE.sub("", text)


# Packages whose writes are the launcher's or the framework's, never the
# prototype's (toga_iOS and the other toga_* backends count too)
LAUNCHER_PACKAGES = frozenset({"mypystub", "toga", "travertino", "rubicon"})


def frame_owner(frame: Any) -> bool | None:
    """Whether code in `frame` is the prototype's: None for the standard library.

    The launcher's and Toga's own code is not the prototype's; anything else
    outside the standard library is.
    """
    name = frame.f_globals.get("__name__") or ""
    top = name.split(".", 1)[0]
    if not top or top in sys.stdlib_module_names:
        return None
    return not (top in LAUNCHER_PACKAGES or top.startswith("toga_"))


def written_by_prototype(frame: Any) -> bool:
    """Whether a write made from `frame` belongs to the running prototype.

    Standard library frames are skipped (print(), traceback, logging and
    warnings write on someone else's behalf), and the first other frame
    decides (see :func:`frame_owner`). With only standard library frames,
    writes on the script thread are the prototype's, and writes on the main
    thread aren't.
    """
    while frame is not None:
        if (owner := frame_owner(frame)) is not None:
            return owner
        frame = frame.f_back
    return threading.current_thread() is not threading.main_thread()


def raised_by_prototype(tb: TracebackType | None) -> bool:
    """Whether a traceback passes through the prototype's code."""
    while tb is not None:
        if frame_owner(tb.tb_frame):
            return True
        tb = tb.tb_next
    return False


def report_exception(
    exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None
) -> None:
    """Write an uncaught exception's full traceback to sys.stderr.

    The launcher's exception hooks write it, so the write itself would be
    the launcher's. During a run, a traceback through the prototype's code
    is shown in the Script tab too, wherever it was caught: on the script
    thread, in a main-thread callback, or in Rubicon's run loop.
    """
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    stream = sys.stderr
    if isinstance(stream, RunStream):
        stream.target.write(text)
        if raised_by_prototype(tb):
            stream.show(text)
    else:
        stream.write(text)


class RunStream(io.TextIOBase):
    """``sys.stdout`` or ``sys.stderr`` during a run: a tee.

    Every write goes to the stream it replaced (the app's log) as it was.
    Writes by the prototype (see :func:`written_by_prototype`) are also passed
    to `show`.
    """

    def __init__(self, target: Any, show: Callable[[str], None]) -> None:
        """Tee writes to `target` and, for the prototype's, to `show`."""
        self.target = target
        self.show = show

    def write(self, s: str) -> int:
        """Write to the log, and show the prototype's writes."""
        self.target.write(s)
        if s and written_by_prototype(sys._getframe(1)):
            self.show(s)
        return len(s)

    def flush(self) -> None:
        """Flush the log."""
        self.target.flush()

    def writable(self) -> bool:
        """It's an output stream."""
        return True

    def isatty(self) -> bool:
        """Not a terminal: no full-screen or cursor tricks can be shown."""
        return False

    @property
    def encoding(self) -> str:  # type: ignore[override]
        """The log's encoding."""
        return getattr(self.target, "encoding", None) or "utf-8"

    def fileno(self) -> int:
        """The log's file descriptor, if it has one."""
        return self.target.fileno()

    def __getattr__(self, name: str) -> Any:
        """Anything else is the log's, such as the log file's ``path``."""
        if name == "target":
            raise AttributeError(name)
        return getattr(self.target, name)


class ScriptRunner:
    """
    Mechanism for "background" execution of further Python code without resorting to subprocess.

    Applies hooks to integrate I/O with the Toga UI.
    """

    def __init__(
        self,
        app: toga.App,
        input_label: toga.Label,
        input_field: toga.TextInput,
        print_field: toga.MultilineTextInput,
        toggle_input: Callable[[bool], None],
        toggle_print: Callable[[bool], None],
        on_error_output: Callable[[str], None] | None = None,
    ) -> None:
        """
        Creates the script bridge that combines hooks with access to Toga widgets
        into which input and print are managed.

        `on_error_output` shows the prototype's stderr text; it's called on the
        main thread. Without it, stderr goes to the log only.
        """
        self.app = app
        self.input_label = input_label
        self.input_field = input_field
        self.print_field = print_field
        # self.scroll = scroll
        self.toggle_input = toggle_input
        self.toggle_print = toggle_print
        self.on_error_output = on_error_output
        self.input_field.on_confirm = self.handle_ui_submit
        # Sync primitives
        self._input_event = threading.Event()
        self._input_value = ""

        # Keep track of the originals, put back when a run ends
        self._original_print = builtins.print
        self._original_input = builtins.input
        self._original_streams: tuple[Any, Any] | None = None
        # Whether the current run has shown any output in the Script tab
        self.printed = False

    def begin_run(self) -> None:
        """Start capturing a run's output. Call on the loop thread.

        print and input stay hooked until end_run, not just while the script's
        body runs, so output from its main-thread callbacks and takeovers is
        shown and counted too (#64).
        """
        self.printed = False
        self.hook_builtins()

    def end_run(self) -> None:
        """Stop capturing output."""
        self.unhook_builtins()

    def hook_builtins(self) -> None:
        """Intercept input, and tee sys.stdout and sys.stderr."""
        builtins.input = self._custom_input
        if self._original_streams is None:
            self._original_streams = (sys.stdout, sys.stderr)
            sys.stdout = RunStream(sys.stdout, self.append_to_log)
            sys.stderr = RunStream(sys.stderr, self.append_error)

    def unhook_builtins(self) -> None:
        """Restore default terminal behavior."""
        builtins.input = self._original_input
        if self._original_streams is not None:
            sys.stdout, sys.stderr = self._original_streams
            self._original_streams = None

    def mainthread_append_to_log(self, message: str) -> None:
        """
        The main thread operation of appending new print data to the onscreen log.
        """
        if w := self.print_field:
            if self.toggle_print(not w.value) and message:
                self.toggle_print(True)
            w.value += message
            if message:
                self.printed = True
            # self.print_field.refresh()
            # await asyncio.sleep(0.01)
            # self.scroll.vertical_position = self.scroll.max_vertical_position

    def append_to_log(self, message: str) -> None:
        """Show the prototype's stdout text in the Script tab, from any thread.

        The text has already gone to the log (see RunStream).
        """
        self._on_main_thread(self.mainthread_append_to_log, clean_ansi(message))

    def append_error(self, message: str) -> None:
        """Show the prototype's stderr text, from any thread."""
        self._on_main_thread(self.mainthread_append_error, clean_ansi(message))

    def mainthread_append_error(self, message: str) -> None:
        """The main thread part of showing stderr text."""
        if message and self.on_error_output is not None:
            self.on_error_output(message)
            self.printed = True

    def _on_main_thread(self, callback: Callable[[str], None], message: str) -> None:
        if threading.current_thread() is threading.main_thread():
            # A script callback on the loop: append now, so the output is
            # counted before any end-of-run check queued after it (#64)
            callback(message)
        else:
            # From the script thread: only call_soon_threadsafe wakes the loop
            # and keeps output ordered with the run's end
            self.app.loop.call_soon_threadsafe(callback, message)

    def _custom_input(self, prompt: object = "") -> str:
        """
        Alternative version of input that sends the prompt to the user and
        accesses a value via a Toga Label and TextInput. Threading locking
        is used to meet the usual guarantee that input is blocking, and "enter"
        or confirmation (rather than incremental changes) are used as the
        trigger that the user is done.
        """
        # 1. Clear any old event state
        self._input_event.clear()
        self._input_value = ""

        # 2. Update and show UI on the main thread
        def setup_ui() -> None:
            """
            Modifies the onscreen UI to show the input field and prompt
            """
            self.toggle_input(True)
            if prompt:
                self.input_label.text = str(prompt)

            self.input_field.value = ""
            self.input_field.focus()

        if app := toga.App.app:
            app.loop.call_soon_threadsafe(setup_ui)

            # 3. Block the student's background thread until the event is set
            self._input_event.wait()

        # 4. Return the captured value back to the student's script
        return self._input_value

    def handle_ui_submit(self, widget: toga.Widget, **kwargs: Any) -> None:
        """Triggered by the Toga TextInput's on_confirm handler."""
        # Capture the text
        self._input_value = self.input_field.value

        self.toggle_input(False)

        # Release the background thread's lock
        self._input_event.set()

    def run_student_script(self, script_func: Callable[[], None]) -> None:
        """Executes the target script function in a background thread."""

        # Start the persistent background timer loop
        # self._auto_scroll = asyncio.create_task(self._auto_scroll_loop())
        def worker() -> None:
            """
            The synchronous operation of the secondary Python script occurs here.
            """
            print("In worker...")
            try:
                script_func()
            finally:
                print("Back out of worker")

        thread = threading.Thread(target=worker, daemon=True)
        print("About to start worker...")
        thread.start()
