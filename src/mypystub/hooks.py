"""
Module of functions for hooking/monkey-patching APIs for our purposes.
This includes redirecting input and print into Toga windowed I/O.
"""

import builtins
import io
import re
import threading
import toga
from typing import Any, Callable

# Regex pattern to match standard ANSI escape sequences (like \x1b[31m)
ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def clean_ansi(text: str) -> str:
    """Removes ANSI color and formatting codes from a string."""
    return ANSI_ESCAPE_RE.sub("", text)


class TogaStream(io.TextIOBase):
    """
    An I/O stream that will integrate with Toga widgets.
    """

    def __init__(
        self, on_write_callback: Callable[[str], None], wait_for_flush: bool = False
    ) -> None:
        """
        Creates the Toga Stream, on_write_callback is a function that accepts a string
        and updates the Toga GUI safely.
        """
        self.pending = ""
        self.on_write_callback = on_write_callback
        self.wait_for_flush = wait_for_flush

    def write(self, s: str) -> int:
        """
        Write the string and return the number of characters "consumed".
        """
        s = clean_ansi(s)
        if s:  # Avoid empty writes
            if self.wait_for_flush:
                self.pending += s
            else:
                self.on_write_callback(s)
        return len(s)

    def flush(self) -> None:
        """
        Trigger to flush the stream.

        Builtin print occasionally calls flush(); we can treat it as a no-op
        or use it as a way to ensure we don't overload the threading crosstalk,
        but in use we didn't see it firing enough and so relying upon it was
        preventing us from printing to the screen, so we do not require it.
        """
        if self.pending:
            self.on_write_callback(self.pending)
            self.pending = ""


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
    ) -> None:
        """
        Creates the script bridge that combines hooks with access to Toga widgets
        into which input and print are managed.
        """
        self.app = app
        self.input_label = input_label
        self.input_field = input_field
        self.print_field = print_field
        # self.scroll = scroll
        self.toggle_input = toggle_input
        self.toggle_print = toggle_print
        self.input_field.on_confirm = self.handle_ui_submit
        # Sync primitives
        self._input_event = threading.Event()
        self._input_value = ""

        # Keep track of original builtins
        self._original_print = builtins.print
        self._original_input = builtins.input

        self.stream = TogaStream(self.append_to_log)

    def hook_builtins(self) -> None:
        """Intercept print and input."""
        builtins.print = self._custom_print
        builtins.input = self._custom_input

    def unhook_builtins(self) -> None:
        """Restore default terminal behavior."""
        builtins.print = self._original_print
        builtins.input = self._original_input

    def mainthread_append_to_log(self, message: str) -> None:
        """
        The main thread operation of appending new print data to the onscreen log.
        """
        if w := self.print_field:
            if self.toggle_print(not w.value) and message:
                self.toggle_print(True)
            w.value += message
            # self.print_field.refresh()
            # await asyncio.sleep(0.01)
            # self.scroll.vertical_position = self.scroll.max_vertical_position

    def append_to_log(self, message: str) -> None:
        """
        Safely appends a message to the UI log view.
        The @ui.main_thread decorator guarantees this executes safely on
        the main thread, even when called from a background thread.
        """
        self._original_print(message)
        self.app.loop.call_soon(lambda: self.mainthread_append_to_log(message))
        # asyncio.create_task(self.mainthread_append_to_log(message))

    def _custom_print(self, *args: Any, **kwargs: Any) -> None:
        """Generic print wrapper that hijacks the 'file' target."""
        # Check if the student explicitly passed a file argument
        # target_file = kwargs.get("file", None)

        # If they didn't specify a file, or they specified standard output,
        # redirect it to our custom Toga stream handler.
        # if target_file is None or target_file in (sys.stdout, sys.__stdout__):
        kwargs["file"] = self.stream

        # Pass everything (positionals, sep, end, flush, and our modified file)
        # down to the native builtin print logic.
        self._original_print(*args, **kwargs)

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
            app.loop.call_soon(setup_ui)

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
            self.hook_builtins()
            try:
                script_func()
            finally:
                self.unhook_builtins()
                print("Back out of worker")

        thread = threading.Thread(target=worker, daemon=True)
        print("About to start worker...")
        thread.start()
