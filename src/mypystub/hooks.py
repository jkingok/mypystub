"""
Module of functions for hooking/monkey-patching APIs for our purposes.

During a run, ``input`` and ``getpass.getpass`` read from the Script tab
(what was asked and answered is echoed there and in the log, except a
password), and ``sys.stdout`` and
``sys.stderr`` are teed: everything still goes to the app's log, unchanged,
and what the prototype writes is also shown in the Script tab, with stderr
shown separately (#119).
"""

from __future__ import annotations

import builtins
import codecs
import getpass
import io
import logging
import re
import sys
import threading
import traceback
from collections.abc import Callable, Iterator
from types import TracebackType
from typing import Any

import toga

log = logging.getLogger(__name__)

EOT, ETX = "\x04", "\x03"  # Ctrl-D and Ctrl-C, as a console delivers them

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


class ConsoleStdin(io.TextIOBase):
    """``sys.stdin`` while the Experimental Console is used: what is typed.

    The console delivers whole lines (and a paste's several lines at once);
    reads wait on the script's thread until there is enough. After
    :meth:`feed_eof` reads return what is left, then "". :meth:`interrupt`
    makes a waiting read raise KeyboardInterrupt, as Ctrl-C would.

    `wait_callback`, if given, is told when a read starts waiting for typing (True)
    and when it has what it needs (False), on the reading thread (#306). A
    read that's already satisfied, by lines typed ahead, doesn't wait at all.
    """

    def __init__(self, wait_callback: Callable[[bool], None] | None = None) -> None:
        """An empty stream, open until fed EOF."""
        self.wait_callback = wait_callback
        self._encoding = "utf-8"
        self._errors = "strict"
        self._binary = BinaryIn(self)
        self._buffer = ""
        self._eof = False
        self._interrupted = False
        self._ready = threading.Condition()

    def feed(self, text: str) -> None:
        """Add typed text, waking a waiting read."""
        with self._ready:
            self._buffer += text
            self._ready.notify_all()

    def feed_eof(self) -> None:
        """No more input: reads return what is left, then ""."""
        with self._ready:
            self._eof = True
            self._ready.notify_all()

    def interrupt(self) -> None:
        """Make a waiting read raise KeyboardInterrupt."""
        with self._ready:
            self._interrupted = True
            self._ready.notify_all()

    def _wait(self, done: Callable[[], bool]) -> None:
        def ready() -> bool:
            return done() or self._eof or self._interrupted

        with self._ready:
            if ready():
                waited = False
            else:
                waited = True
                if self.wait_callback is not None:
                    self.wait_callback(True)
                while not ready():
                    self._ready.wait()
            interrupted, self._interrupted = self._interrupted, False
        if waited and self.wait_callback is not None:
            self.wait_callback(False)
        if interrupted:
            raise KeyboardInterrupt

    def readline(self, size: int | None = -1) -> str:  # type: ignore[override]
        """The next line, waiting for it to be typed."""
        self._wait(lambda: "\n" in self._buffer)
        with self._ready:
            end = self._buffer.find("\n") + 1 or len(self._buffer)
            if size is not None and size >= 0:
                end = min(end, size)
            line, self._buffer = self._buffer[:end], self._buffer[end:]
            return line

    def read(self, size: int | None = -1) -> str:
        """`size` characters, or everything until EOF."""
        if size is None or size < 0:
            self._wait(lambda: False)  # until EOF
            wanted = None
        else:
            wanted = size
            self._wait(lambda: len(self._buffer) >= wanted)
        with self._ready:
            end = len(self._buffer) if wanted is None else wanted
            text, self._buffer = self._buffer[:end], self._buffer[end:]
            return text

    def __iter__(self) -> Iterator[str]:
        """Lines until EOF."""
        while line := self.readline():
            yield line

    def readable(self) -> bool:
        """It's an input stream."""
        return True

    def isatty(self) -> bool:
        """Not a terminal, so input() reads a line rather than using readline."""
        return False

    @property
    def buffer(self) -> BinaryIn:
        """The binary side, as ``sys.stdin.buffer`` is (#300)."""
        return self._binary

    @property
    def encoding(self) -> str:  # type: ignore[override]
        """How typed text is encoded for `buffer`."""
        return self._encoding

    @property
    def errors(self) -> str:  # type: ignore[override]
        """The error handler for `buffer`'s encoding."""
        return self._errors

    @property
    def line_buffering(self) -> bool:
        """Input is line by line anyway."""
        return False

    @property
    def write_through(self) -> bool:
        """Not an output stream; False, as for a real stdin."""
        return False

    def reconfigure(
        self,
        *,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
        line_buffering: bool | None = None,
        write_through: bool | None = None,
    ) -> None:
        """As ``TextIOWrapper.reconfigure``: records the encoding and errors."""
        if encoding is not None:
            codecs.lookup(encoding)
            self._encoding = encoding
        if errors is not None:
            codecs.lookup_error(errors)
            self._errors = errors
        if newline not in (None, "", "\n", "\r", "\r\n"):
            raise ValueError(f"illegal newline value: {newline!r}")


class BinaryIn(io.BufferedIOBase):
    """``sys.stdin.buffer`` for :class:`ConsoleStdin`: typed text, encoded."""

    def __init__(self, stream: ConsoleStdin) -> None:
        """Bytes read here come from `stream`."""
        super().__init__()
        self.stream = stream
        self._pending = b""  # encoded but not yet read (a partial read)

    def _encode(self, text: str) -> bytes:
        return text.encode(self.stream.encoding, self.stream.errors)

    def read(self, size: int | None = -1) -> bytes:
        """Up to `size` bytes, waiting for typing; everything until EOF if < 0."""
        if size is None or size < 0:
            data, self._pending = self._pending + self._encode(self.stream.read()), b""
            return data
        while len(self._pending) < size:
            line = self.stream.readline()
            if not line:
                break
            self._pending += self._encode(line)
        data, self._pending = self._pending[:size], self._pending[size:]
        return data

    def read1(self, size: int = -1) -> bytes:
        """What is waiting, or the next line typed: at most `size` bytes."""
        if not self._pending:
            self._pending = self._encode(self.stream.readline())
        if size < 0:
            size = len(self._pending)
        data, self._pending = self._pending[:size], self._pending[size:]
        return data

    def readline(self, size: int | None = -1) -> bytes:
        """The next line, as bytes."""
        if b"\n" not in self._pending:
            self._pending += self._encode(self.stream.readline())
        end = self._pending.find(b"\n") + 1 or len(self._pending)
        if size is not None and size >= 0:
            end = min(end, size)
        data, self._pending = self._pending[:end], self._pending[end:]
        return data

    def readinto(self, buffer: Any) -> int:
        """Fill `buffer` with what read1() gives."""
        view = memoryview(buffer).cast("B")
        data = self.read1(len(view))
        view[: len(data)] = data
        return len(data)

    def readable(self) -> bool:
        """It's an input stream."""
        return True


class BinaryOut(io.BufferedIOBase):
    """``sys.stdout.buffer`` (or ``stderr``'s) during a run: bytes to a RunStream.

    Bytes are decoded as they come, keeping a character split between two
    writes, and pass through the same show-and-log path as text. Whether they
    are the prototype's is decided from *this* write's caller, as RunStream
    does for text, since a wrapper between them would otherwise be the caller.
    """

    def __init__(self, stream: RunStream) -> None:
        """Bytes written here go to `stream`."""
        super().__init__()
        self.stream = stream
        self._decoder = stream.new_decoder()

    def write(self, data: Any) -> int:
        """Decode `data` and pass it on, as written to the text stream."""
        raw = bytes(data)
        text = self._decoder.decode(raw)
        if text:
            self.stream.put(text, written_by_prototype(sys._getframe(1)))
        return len(raw)

    def flush(self) -> None:
        """Flush the text stream (the log)."""
        self.stream.flush()

    def writable(self) -> bool:
        """It's an output stream."""
        return True

    def reset_decoder(self) -> None:
        """Start decoding afresh, as after ``reconfigure(encoding=...)``."""
        self._decoder = self.stream.new_decoder()


class RunStream(io.TextIOBase):
    """``sys.stdout`` or ``sys.stderr`` during a run: a tee.

    Every write goes to the stream it replaced (the app's log) as it was.
    Writes by the prototype (see :func:`written_by_prototype`) are also passed
    to `show`.

    It also has what scripts expect of a real ``sys.stdout`` (#300): a binary
    ``buffer`` (see :class:`BinaryOut`), and ``reconfigure()``, which records the
    encoding and errors and accepts the buffering options, which change
    nothing here: every write goes straight through.
    """

    def __init__(self, target: Any, show: Callable[[str], None]) -> None:
        """Tee writes to `target` and, for the prototype's, to `show`."""
        self.target = target
        self.show = show
        self._encoding = getattr(target, "encoding", None) or "utf-8"
        self._errors = getattr(target, "errors", None) or "strict"
        self._line_buffering = False
        self._buffer = BinaryOut(self)

    def write(self, s: str) -> int:
        """Write to the log, and show the prototype's writes."""
        self.put(s, bool(s) and written_by_prototype(sys._getframe(1)))
        return len(s)

    def put(self, s: str, shown: bool) -> None:
        """Write `s` to the log, and to `show` if it is the prototype's."""
        self.target.write(s)
        if s and shown:
            self.show(s)

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
    def buffer(self) -> BinaryOut:
        """The binary side, as ``sys.stdout.buffer`` is."""
        return self._buffer

    @property
    def encoding(self) -> str:  # type: ignore[override]
        """The encoding: the log's, or what reconfigure() set."""
        return self._encoding

    @property
    def errors(self) -> str:  # type: ignore[override]
        """The error handler: the log's, or what reconfigure() set."""
        return self._errors

    @property
    def line_buffering(self) -> bool:
        """As reconfigure() set it; every write goes straight through anyway."""
        return self._line_buffering

    @property
    def write_through(self) -> bool:
        """Always: nothing is held back."""
        return True

    def reconfigure(
        self,
        *,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
        line_buffering: bool | None = None,
        write_through: bool | None = None,
    ) -> None:
        """As ``TextIOWrapper.reconfigure``: unknown codecs and handlers raise."""
        if encoding is not None:
            codecs.lookup(encoding)  # LookupError, as TextIOWrapper raises
            self._encoding = encoding
            if errors is None:
                self._errors = "strict"
        if errors is not None:
            codecs.lookup_error(errors)
            self._errors = errors
        if newline not in (None, "", "\n", "\r", "\r\n"):
            raise ValueError(f"illegal newline value: {newline!r}")
        if line_buffering is not None:
            self._line_buffering = bool(line_buffering)
        self._buffer.reset_decoder()

    def new_decoder(self) -> codecs.IncrementalDecoder:
        """A decoder for bytes written to `buffer`: undecodable bytes show as \ufffd."""
        return codecs.getincrementaldecoder(self._encoding)(errors="replace")

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
        password_label: toga.Label | None = None,
        password_field: toga.PasswordInput | None = None,
        toggle_password: Callable[[bool], None] | None = None,
        on_console_wait: Callable[[bool], None] | None = None,
    ) -> None:
        """
        Creates the script bridge that combines hooks with access to Toga widgets
        into which input and print are managed.

        `on_error_output` shows the prototype's stderr text; it's called on the
        main thread. Without it, stderr goes to the log only.

        `password_label`, `password_field` and `toggle_password` are the widgets
        ``getpass.getpass`` uses, so a password isn't shown as it is typed.
        Without them, getpass uses the text field but never echoes the answer.
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
        self.password_label = password_label
        self.password_field = password_field
        self.toggle_password = toggle_password
        if password_field is not None:
            password_field.on_confirm = self.handle_ui_submit
        # What the question in progress is, for the echo
        self._prompt = ""
        self._secret = False
        self._toggle_current: Callable[[bool], None] | None = None
        # Sync primitives
        self._input_event = threading.Event()
        self._input_value = ""

        # Keep track of the originals, put back when a run ends
        self._original_print = builtins.print
        self._original_input = builtins.input
        self._original_getpass = getpass.getpass
        self._original_streams: tuple[Any, Any] | None = None
        # Whether the current run has shown any output in the Script tab
        self.printed = False
        # Setup's Experimental Console: a toga-console Console that shows the
        # run's output and answers input() instead of print_field and
        # input_field. Chosen per run by the launcher (None: not used).
        self.console: Any = None
        # Told on the main thread when the console's stdin starts or stops
        # waiting for typing (#306)
        self.on_console_wait = on_console_wait
        # The run's sys.stdin while the console is used, fed by what is typed
        self._console_stdin: ConsoleStdin | None = None
        self._original_stdin: Any = None

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
        """Intercept input and getpass, and tee sys.stdout and sys.stderr.

        With the Experimental Console, input() isn't hooked: the console is
        typeable for the whole run and feeds ``sys.stdin``, so Python's own
        input() (and anything else reading stdin) works as at a terminal.
        getpass() keeps its password field, since the console echoes.
        """
        getpass.getpass = self._custom_getpass
        if self.console is None:
            builtins.input = self._custom_input
        elif self._console_stdin is None:
            self._console_stdin = ConsoleStdin(wait_callback=self._console_wait)
            self._original_stdin = sys.stdin
            sys.stdin = self._console_stdin  # type: ignore[assignment]
            self.console.on_input = self.handle_console_input
            self.console.readonly = False
        if self._original_streams is None:
            self._original_streams = (sys.stdout, sys.stderr)
            sys.stdout = RunStream(sys.stdout, self.append_to_log)
            sys.stderr = RunStream(sys.stderr, self.append_error)

    def unhook_builtins(self) -> None:
        """Restore default terminal behavior."""
        builtins.input = self._original_input
        getpass.getpass = self._original_getpass
        if self._console_stdin is not None:
            self._console_stdin.feed_eof()  # a read still waiting ends
            sys.stdin = self._original_stdin
            self._console_stdin = None
            if self.console is not None:
                self.console.readonly = True
        if self._original_streams is not None:
            sys.stdout, sys.stderr = self._original_streams
            self._original_streams = None

    def mainthread_append_to_log(self, message: str) -> None:
        """
        The main thread operation of appending new print data to the onscreen log.
        """
        if self.console is not None:
            if message:
                self.console.write(message)
                self.printed = True
            return
        if w := self.print_field:
            if self.toggle_print(not w.value) and message:
                self.toggle_print(True)
            w.value += message
            if message:
                self.printed = True
                # Follow the output, as a terminal does: the newest line shows
                # even when the pane is short, such as above the keyboard
                scroll = getattr(w, "scroll_to_bottom", None)
                if scroll is not None:
                    scroll()

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
        if message and self.console is not None:
            self.console.write(message, stream="stderr")  # red, in the same view
            self.printed = True
            return
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
        """Alternative version of input: the prompt and answer are echoed.

        The prompt is shown in a label above a text field. Threading locking
        is used to meet the usual guarantee that input is blocking, and "enter"
        or confirmation (rather than incremental changes) are used as the
        trigger that the user is done. As a terminal would, the prompt and the
        typed answer are then written to the output and the log.
        """
        return self._ask(str(prompt), secret=False)

    def _custom_getpass(self, prompt: str = "Password: ", stream: Any = None) -> str:
        """Alternative version of getpass.getpass: a password field, no echo.

        Only the prompt (and a newline) reaches the output and the log. `stream`
        is accepted for compatibility and ignored.
        """
        return self._ask(str(prompt), secret=True)

    def _ask(self, prompt: str, secret: bool) -> str:
        """Ask the user a question and wait on the script thread for the answer."""
        use_password = secret and self.password_field is not None
        label = self.password_label if use_password else self.input_label
        field = self.password_field if use_password else self.input_field
        toggle = self.toggle_password if use_password else self.toggle_input

        # 1. Clear any old event state
        self._input_event.clear()
        self._input_value = ""
        self._prompt = prompt
        self._secret = secret
        self._toggle_current = toggle

        # 2. Update and show UI on the main thread
        def setup_ui() -> None:
            """
            Modifies the onscreen UI to show the input field and prompt
            """
            if toggle is not None:
                toggle(True)
            if prompt and label is not None:
                label.text = prompt

            if field is not None:
                field.value = ""
                field.focus()

        if self.app is not None and getattr(self.app, "loop", None) is not None:
            self.app.loop.call_soon_threadsafe(setup_ui)

            # 3. Block the student's background thread until the event is set
            self._input_event.wait()

        # 4. Return the captured value back to the student's script
        return self._input_value

    def _console_wait(self, waiting: bool) -> None:
        """From the reading thread: pass the wait on to the main thread."""
        if self.on_console_wait is not None and self.app is not None:
            self.app.loop.call_soon_threadsafe(self.on_console_wait, waiting)

    def handle_console_input(self, widget: Any, data: bytes, **kwargs: Any) -> None:
        """The console's on_input: typed lines go to the run's ``sys.stdin``.

        Ctrl-D ends stdin (EOF) and Ctrl-C interrupts a read that's waiting, as
        at a terminal. Lines typed before the prototype asks wait their turn.
        """
        stdin = self._console_stdin
        if stdin is None:
            return
        text = data.decode("utf-8", errors="replace")
        if text == EOT:
            stdin.feed_eof()
        elif text == ETX:
            stdin.interrupt()
        else:
            stdin.feed(text)
            self._log(text)  # the console shows it; the log gets it too

    def _log(self, text: str) -> None:
        """Write `text` to the app's log only."""
        self.log_only(text)

    def log_only(self, text: str, error: bool = False) -> None:
        """Write `text` to the app's log (not the Script tab) during a run."""
        streams = self._original_streams or (sys.stdout, sys.stderr)
        streams[1 if error else 0].write(text)

    def echo_answer(self) -> None:
        """Write the question and answer, as a terminal would, to screen and log.

        A password's value is never written: only the prompt and a newline.
        """
        text = self._prompt + ("" if self._secret else self._input_value) + "\n"
        # The log gets it directly: writing to sys.stdout from here would be
        # the launcher's own, which is log-only anyway
        log = (self._original_streams or (sys.stdout,))[0]
        log.write(text)
        self.mainthread_append_to_log(clean_ansi(text))

    def handle_ui_submit(self, widget: toga.Widget, **kwargs: Any) -> None:
        """Triggered by the Toga TextInput's or PasswordInput's on_confirm handler."""
        # Capture the text
        self._input_value = str(getattr(widget, "value", ""))

        self.echo_answer()
        if self._toggle_current is not None:
            self._toggle_current(False)
        if self._secret and self.password_field is not None:
            self.password_field.value = ""  # don't leave the password in the widget

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
            log.debug("In worker...")
            try:
                script_func()
            finally:
                log.debug("Back out of worker")

        thread = threading.Thread(target=worker, daemon=True)
        log.debug("About to start worker...")
        thread.start()
