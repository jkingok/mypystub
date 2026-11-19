"""Start App Template as an app of its own: a small copy of MyPyStub's Script tab.

In MyPyStub the launcher already gives the app a window, its output, a log,
``input()``, Back and error reports, so :func:`main` only calls ``app.main()``.
As an app of its own (``briefcase dev``, or built for iOS, Android or a
computer) it does that part itself:

- **A Script view** (script_view.py): what the app prints, ``input()`` and
  ``getpass()``, and a **Restart** button. ``main()`` runs on a thread of its
  own, as a script does in MyPyStub, so ``input()`` can wait. The app takes the
  window over; the Script view comes back only if it asks a question, stops
  with an error, or finishes without showing anything.
- **A log:** everything printed also goes to ``app_runtime.log`` in the app's
  Documents (the same folder MyPyStub uses, shown in the Files app), emptied
  at each start.
- **Back on Android** (android_back.py): goes back through the window's
  ``content_stack``, the takeover protocol MyPyStub uses, when the app keeps
  one; otherwise Android's usual Back.

It needs only Toga, so it builds unchanged with Briefcase.
"""

from __future__ import annotations

import sys
import threading
import traceback
from pathlib import Path
from typing import Any

import toga

from app_template import app as the_app
from app_template.script_view import ScriptView

FORMAL_NAME = "App Template"
APP_ID = "com.example.app_template"
LOG_NAME = "app_runtime.log"


def documents_dir() -> Path:
    """The app's Documents folder, where MyPyStub keeps its own."""
    if sys.platform == "android":
        try:
            from com.chaquo.python import Python  # type: ignore[import-not-found]

            files = Python.getPlatform().getApplication().getFilesDir()
            return Path(files.getAbsolutePath())
        except Exception as error:  # noqa: BLE001  (not under Chaquopy after all)
            print(f"Using ~/Documents: {error}")
    return Path("~/Documents").expanduser()


class Bootstrap(toga.App):
    """The window, log, input and error handling around the app."""

    def startup(self) -> None:
        """Show the Script view, then start the app."""
        docs = documents_dir()
        docs.mkdir(parents=True, exist_ok=True)
        self.script = ScriptView(self, self.run_app)
        # Emptied each start, so it can't grow without limit
        log = (docs / LOG_NAME).open("w", encoding="utf-8", buffering=1)
        self.script.hook(log)

        self.window = toga.MainWindow(title=self.formal_name)
        self.window.content = self.script.box
        self.main_window = self.window

        # Errors anywhere (the app's handlers, its threads) come back here
        self.loop.set_exception_handler(
            lambda loop, context: self.failed(context.get("exception"))
        )
        sys.excepthook = lambda kind, error, tb: self.failed(error)
        threading.excepthook = lambda args: self.loop.call_soon_threadsafe(
            self.failed, args.exc_value
        )
        if sys.platform == "android":
            from app_template import android_back

            android_back.install(self.go_back)
        self.window.show()
        self.loop.call_soon(self.run_app)

    def go_back(self) -> bool:
        """Android's Back: the app's previous screen, if it keeps a stack."""
        stack: list[Any] | None = getattr(self.window, "content_stack", None)
        if not stack:
            return False
        self.window.title, self.window.content = stack.pop()
        return True

    def run_app(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Run the app's ``main()`` on its own thread; it takes the window over."""
        self.script.restart.enabled = False
        self.script.status.text = "Running"
        self.window.title = self.formal_name
        self.window.content = self.script.box
        threading.Thread(target=self.run_main, name="main()", daemon=True).start()

    def run_main(self) -> None:
        """The app's thread: ``main()``, then see whether it showed anything."""
        try:
            the_app.main()
        except SystemExit as stop:
            if stop.code not in (None, 0):
                self.loop.call_soon_threadsafe(self.failed, stop)
                return
        except BaseException as error:  # noqa: BLE001  (shown, then Restart)
            self.loop.call_soon_threadsafe(self.failed, error)
            return
        # The app's screen is made on a later turn of the loop; look after it
        self.loop.call_soon_threadsafe(self.loop.call_soon, self.check_finished)

    def check_finished(self) -> None:
        """If the app showed nothing, it has finished: offer to run it again."""
        if self.window.content is self.script.box:
            self.script.status.text = "Finished"
            self.script.restart.enabled = True

    def failed(self, error: BaseException | None) -> None:
        """Show the error in the Script view, with Restart."""
        if error is not None:
            print("".join(traceback.format_exception(error)), file=sys.stderr)
        self.window.title = self.formal_name
        self.window.content = self.script.box
        self.script.status.text = "Stopped with an error"
        self.script.restart.enabled = True


def main() -> Bootstrap | None:
    """Start the app, or, inside MyPyStub (an app already running), just run it."""
    if toga.App.app is not None:
        the_app.main()
        return None
    return Bootstrap(formal_name=FORMAL_NAME, app_id=APP_ID)
