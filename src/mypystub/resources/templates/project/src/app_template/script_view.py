"""The Script view: what the app prints, and where ``input()`` gets its answer.

A small copy of MyPyStub's Script tab, needing only Toga. While the app runs:

- ``print`` (and anything written to ``sys.stdout`` or ``sys.stderr``) is shown
  here and written to the log;
- ``input()`` shows its prompt above a text field and waits for Return;
- ``getpass.getpass()`` does the same with a password field, and doesn't echo
  the answer.

``input()`` blocks until the answer comes, so the app's ``main()`` runs on a
thread of its own (see bootstrap.py). The widgets are only touched on the main
thread.
"""

from __future__ import annotations

import builtins
import getpass
import sys
import threading
from typing import Any, TextIO

import toga


class Tee:
    """A stream that writes to the console, the log, and the Script view."""

    def __init__(self, console: TextIO | None, log: TextIO, show: Any) -> None:
        """Write to each of these; `show` takes text for the Script view."""
        self.console = console
        self.log = log
        self.show = show

    def write(self, text: str) -> int:
        """Pass `text` on to all three."""
        if self.console:
            self.console.write(text)
        self.log.write(text)
        self.show(text)
        return len(text)

    def flush(self) -> None:
        """Flush the console and the log."""
        if self.console:
            self.console.flush()
        self.log.flush()

    def isatty(self) -> bool:
        """Not a terminal."""
        return False


class ScriptView:
    """The output, the question being asked, and the run's status."""

    def __init__(self, app: toga.App, on_restart: Any) -> None:
        """Make the widgets; `on_restart` runs the app again."""
        self.app = app
        self.output = toga.MultilineTextInput(readonly=True, flex=1)
        self.prompt = toga.Label("")
        self.answer = toga.TextInput(flex=1, on_confirm=self.answered)
        self.secret = toga.PasswordInput(flex=1, on_confirm=self.answered)
        self.question = toga.Column(
            margin=4,
            visibility="hidden",
            children=[self.prompt, self.answer, self.secret],
        )
        self.status = toga.Label("Starting", flex=1)
        self.restart = toga.Button("Restart", on_press=on_restart, enabled=False)
        self.box = toga.Column(
            flex=1,
            children=[
                self.output,
                self.question,
                toga.Row(
                    margin=4, align_items="center", children=[self.status, self.restart]
                ),
            ],
        )
        self._given = threading.Event()
        self._text = ""
        self._covered: tuple[str, Any] | None = (
            None  # the app's screen, if asked over it
        )

    def on_main(self, callback: Any, *args: Any) -> None:
        """Run `callback` on the main thread: now if this is it, else soon."""
        if threading.current_thread() is threading.main_thread():
            callback(*args)
        else:
            self.app.loop.call_soon_threadsafe(callback, *args)

    def show_output(self, text: str) -> None:
        """Add printed text to the view, from any thread."""

        def add() -> None:
            self.output.value += text
            self.output.scroll_to_bottom()

        self.on_main(add)

    def hook(self, log: TextIO) -> None:
        """Send output here and to `log`, and answer input() and getpass()."""
        sys.stdout = Tee(sys.__stdout__, log, self.show_output)  # type: ignore[assignment]
        sys.stderr = Tee(sys.__stderr__, log, self.show_output)  # type: ignore[assignment]
        builtins.input = self.ask
        getpass.getpass = self.ask_secret

    def ask(self, prompt: object = "") -> str:
        """``input()``: show the prompt and wait for the answer; echo both."""
        answer = self._wait(str(prompt), secret=False)
        print(f"{prompt}{answer}")
        return answer

    def ask_secret(self, prompt: str = "Password: ", stream: Any = None) -> str:
        """``getpass.getpass()``: a password field; only the prompt is echoed."""
        answer = self._wait(str(prompt), secret=True)
        print(prompt)
        return answer

    def _wait(self, prompt: str, secret: bool) -> str:
        if threading.current_thread() is threading.main_thread():
            raise RuntimeError("input() would freeze the app on its main thread")
        self._given.clear()

        def show() -> None:
            field = self.secret if secret else self.answer
            self.prompt.text = prompt
            self.answer.style.display = "none" if secret else "pack"
            self.secret.style.display = "pack" if secret else "none"
            field.value = ""
            self.question.visibility = "visible"
            window = self.app.main_window
            assert isinstance(window, toga.Window)
            if window.content is not self.box:
                # Asked after the app took the window: put its screen back after
                self._covered = (window.title, window.content)
                window.content = self.box
            field.focus()

        self.on_main(show)
        self._given.wait()
        return self._text

    def answered(self, widget: toga.Widget, **kwargs: Any) -> None:
        """Return was pressed: hand the answer to the waiting thread."""
        self._text = str(widget.value)
        widget.value = ""
        self.question.visibility = "hidden"
        if self._covered is not None:
            window = self.app.main_window
            assert isinstance(window, toga.Window)
            window.title, window.content = self._covered
            self._covered = None
        self._given.set()
