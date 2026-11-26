"""Start App Template as an app of its own, with MyPyStub's Script view.

In MyPyStub the launcher already gives the app a window, its output, a log,
``input()``, Back and error reports, so :func:`main` only calls ``app.main()``.
As an app of its own (``briefcase dev``, or built for iOS, Android or a
computer) it does that part itself, with the modules it shares with MyPyStub
(don't edit those: an update of the project replaces them):

- **The Script view** (script_tab.py, hooks.py): what the app prints, its
  errors, ``input()`` and ``getpass()``, and how the run ended (run_status.py),
  with a **Restart** button. ``main()`` runs on a thread of its own, as a
  script does in MyPyStub, so ``input()`` can wait. The app takes the window
  over; the Script view comes back if it asks a question, stops with an
  error, or finishes without showing anything.
- **A log** (logfile.py): everything printed also goes to ``app_runtime.log``
  in the app's Documents (the same folder MyPyStub uses), emptied each start.
- **Back on Android** (android_back.py): goes back through the window's
  ``content_stack``, the takeover protocol MyPyStub uses, when the app keeps
  one; otherwise Android's usual Back.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any

import toga

from app_template import app as the_app
from app_template import hooks, logfile
from app_template.run_status import run_status
from app_template.script_tab import ScriptTab

FORMAL_NAME = "App Template"
APP_ID = "com.example.app_template"
LOG_NAME = "app_runtime.log"
# This package's own modules that aren't the app: their writes aren't shown
FRAMEWORK = ("bootstrap", "hooks", "script_tab", "run_status", "logfile")


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
        logfile.install(docs / LOG_NAME).truncate()  # so it can't grow forever
        package = __name__.rpartition(".")[0]
        hooks.set_framework(*(f"{package}.{name}" for name in FRAMEWORK))
        self.window = toga.MainWindow(title=self.formal_name)
        self.main_window = self.window
        self.make_view()
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

    def make_view(self) -> None:
        """The Script view, with Restart under it, and the runner showing in it."""
        self.script = ScriptTab(self)
        self.script.box.style.flex = 1
        self.restart = toga.Button("Restart", on_press=self.run_app, enabled=False)
        self.view = toga.Column(
            flex=1,
            children=[self.script.box, toga.Row(margin=4, children=[self.restart])],
        )
        self.window.content = self.view
        self.runner = self.script.runner()
        # A question asked after the app took the window brings the view back
        self.runner.toggle_input = self.asking(self.script.toggle_input)
        self.runner.toggle_password = self.asking(self.script.toggle_password)
        self.covered: tuple[str, Any] | None = None

    def asking(self, toggle: Any) -> Any:
        """`toggle`, showing the Script view while a question is asked."""

        def show(on: bool) -> None:
            if on and self.window.content is not self.view:
                self.covered = (self.window.title, self.window.content)
                self.window.content = self.view
            toggle(on)
            if not on and self.covered is not None:
                self.window.title, self.window.content = self.covered
                self.covered = None

        return show

    def go_back(self) -> bool:
        """Android's Back: the app's previous screen, if it keeps a stack."""
        stack: list[Any] | None = getattr(self.window, "content_stack", None)
        if not stack:
            return False
        self.window.title, self.window.content = stack.pop()
        return True

    def run_app(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Run the app's ``main()`` on its own thread; it takes the window over."""
        self.restart.enabled = False
        self.script.clear()
        self.script.activity.update("Running", on=True)
        self.window.title = self.formal_name
        self.window.content = self.view
        self.runner.begin_run()
        threading.Thread(target=self.run_main, name="main()", daemon=True).start()

    def run_main(self) -> None:
        """The app's thread: ``main()``, then see whether it showed anything."""
        error: BaseException | None = None
        try:
            the_app.main()
        except BaseException as caught:  # noqa: BLE001  (shown, then Restart)
            error = caught
            if not isinstance(caught, SystemExit):
                hooks.report_exception(type(caught), caught, caught.__traceback__)
        # The app's screen is made on a later turn of the loop; look after it
        self.loop.call_soon_threadsafe(self.loop.call_soon, self.finished, error)

    def finished(self, error: BaseException | None) -> None:
        """``main()`` returned: if it showed nothing, say how it ended."""
        status = run_status(error)
        if status == run_status(None) and self.window.content is not self.view:
            return  # it took the window over and is still running
        self.ended(status)

    def failed(self, error: BaseException | None) -> None:
        """An error in the app's handlers or threads: show it, with Restart."""
        if error is not None:
            hooks.report_exception(type(error), error, error.__traceback__)
        self.ended(run_status(error or RuntimeError()))

    def ended(self, status: str) -> None:
        """Show the Script view with how the run ended, and offer Restart."""
        self.window.title = self.formal_name
        self.window.content = self.view
        self.script.activity.update(status, on=False)
        self.restart.enabled = True


def main() -> Bootstrap | None:
    """Start the app, or, inside MyPyStub (an app already running), just run it."""
    if toga.App.app is not None:
        the_app.main()
        return None
    return Bootstrap(formal_name=FORMAL_NAME, app_id=APP_ID)
