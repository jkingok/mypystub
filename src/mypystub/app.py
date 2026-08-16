"""
Application initialization, log redirection, and dynamic hot-patching runtime.

Manages application startup (`MyApp`), redirects standard output/error to disk (`LogRedirector`),
and checks the iOS user sandbox (`~/Documents/patch_app.py`) for live runtime overrides.
"""

import asyncio
import sys
import threading
import traceback
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import Any, cast

import toga

from . import ui


class LogRedirector:
    """
    Redirects Python stdout and stderr streams to both standard output and a persistent file log.

    :param log_path: Path to target log file on disk.
    :type log_path: str | Path
    """

    def __init__(self, log_path: Path):
        """
        Creates the log redirector that will duplicate output to the given log_path.
        """
        self.log_path = log_path or Path("./app_runtime.log")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_path.open(mode="a", buffering=1, encoding="utf-8")
        self.terminal = sys.__stdout__  # both out and err end up in out

    def isatty(self) -> bool:
        # Hopefully this only prevents fancy not all input!
        return False

    @property
    def path(self) -> Path:
        return self.log_path

    def write(self, message: str) -> None:
        """
        Writes a message string to terminal stdout and log file simultaneously.

        :param message: String output message.
        :type message: str
        """
        if self.terminal:
            self.terminal.write(message)
        self.log_file.write(message)

    def flush(self) -> None:
        """
        Flushes terminal and log file buffers.
        """
        if self.terminal:
            self.terminal.flush()
        self.log_file.flush()


class MyApp(toga.App):
    """
    Main Toga Application instance
    """
    def __init__(self, user_documents_dir: Path | None = None, **kwargs: Any):
        """
        Initializes the Toga application instance.

        :param user_documents_dir: Optional path to user Documents folder for log redirection.
        :type user_documents_dir: Path | None
        :param kwargs: Additional keyword arguments for Toga App initialization.
        """
        self.user_documents_dir = user_documents_dir or Path("~/Documents").expanduser()
        super().__init__(**kwargs)

    @staticmethod
    def startup_into(app: toga.App, fresh: bool = False) -> None:
        """
        Constructs and presents the application main window and prototype layout.

        :param app: Toga application instance.
        :type app: toga.App
        :param fresh: True if creating the MainWindow for the first time.
        :type fresh: bool
        """
        if fresh:
            app.main_window = toga.MainWindow(title=app.formal_name)
        mw = app.main_window
        assert isinstance(mw, toga.MainWindow)

        def global_generic_exception_handler(
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            exc_traceback: TracebackType | None,
            exc_message: str | None = None,
        ) -> None:
            """
            Generic handler of uncaught exceptions into a Toga dialog via a threadsafe task.
            """
            if exc_traceback:
                traceback.print_tb(exc_traceback)
            app.loop.call_soon_threadsafe(
                cast(
                    Callable[[], None],
                    lambda mw=mw: asyncio.create_task(
                        mw.dialog(
                            toga.ErrorDialog(
                                "Error Occurred",
                                exc_message if exc_message else str(exc_value),
                            )
                        )
                    ),
                )
            )

        def global_async_exception_handler(
            _loop: asyncio.AbstractEventLoop, context: dict[str, Any]
        ) -> None:
            """
            Trigger for uncaught exceptions via the asyncio event loop.
            """
            global_generic_exception_handler(
                None, context.get("exception"), context.get("source_traceback")
            )

        def global_sync_exception_handler(
            exc_type: type[BaseException],
            exc_value: BaseException,
            exc_traceback: TracebackType | None,
        ) -> None:
            """
            Trigger for normal uncaught exceptions.
            """
            global_generic_exception_handler(exc_type, exc_value, exc_traceback)

        def global_thread_exception_handler(args: threading.ExceptHookArgs) -> None:
            """
            Trigger for threaded uncaught exceptions.
            """
            global_generic_exception_handler(
                args.exc_type, args.exc_value, args.exc_traceback
            )

        # Set up standard Python thread hooks
        sys.excepthook = global_sync_exception_handler
        threading.excepthook = global_thread_exception_handler

        # Attach custom handler to Toga's asyncio loop
        loop = asyncio.get_event_loop()
        loop.set_exception_handler(global_async_exception_handler)

        try:
            app.proto = (p := ui.Prototype(host_app=app, on_done=lambda _: MyApp.unstack_from(app))) # pyright: ignore [reportAttributeAccessIssue]

            t = p.title or app.formal_name
            if mw.content:
                if not hasattr(mw, "content_stack"):
                    mw.content_stack = [] # pyright: ignore [reportAttributeAccessIssue]
                getattr(mw, "content_stack", []).append((mw.title, mw.content))
            mw.title = t
            mw.content = p.get_content()
        except Exception as e: # noqa: BLE001
            traceback.print_exc()
            app.loop.create_task(mw.dialog(toga.ErrorDialog("Error Occurred", str(e))))
        finally:
            if not mw.visible:
                mw.show()

    @staticmethod
    def unstack_from(app: toga.App) -> None:
        """
        Pops and restores the previous window view layout from the content stack.

        :param app: Toga application instance.
        :type app: toga.App
        """
        if (
            hasattr(mw := app.main_window, "content_stack")
            and len(cs := getattr(mw, "content_stack", [])) > 0
        ):
            t, c = cs.pop()
            assert isinstance(mw, toga.MainWindow)
            mw.title = t
            mw.content = c

    def startup(self) -> None:
        """
        Standard Toga application startup callback. Initializes main window and UI content.

        :returns: Result of :meth:`startup_into`.
        """
        MyApp.startup_into(self, True)


def bootstrap_application() -> Any:
    """
    Bootstraps the application environment on device launch.

    Sets up stdout/stderr logging in `~/Documents/app_runtime.log`.
    If an updated `patch_app.py` script exists in the iOS user Documents folder,
    it executes `patch_app.main()` to allow live code updates without recompiling.
    Otherwise, returns a standard :class:`MyApp` instance.

    :returns: Application instance or result of `patch_app.main()`.
    :rtype: toga.App
    """

    # This is equivalent to the toga.App.app.paths.data on many platforms
    if sys.platform == "android":

        user_documents_dir = Path(".")  # Default to current directory on Android as a fallback

        from com.chaquo.python import Python
        context = Python.getPlatform().getApplication()
        
        if context is not None:
            #external_files_dir = context.getExternalFilesDir("Documents")
            #if external_files_dir is not None:
            files_dir = context.getFilesDir()
            user_documents_dir = Path(files_dir.getAbsolutePath())
    else:
        user_documents_dir = Path("~/Documents").expanduser()
    user_documents_dir.mkdir(parents=True, exist_ok=True)

    log_path = user_documents_dir / "app_runtime.log"

    redirector = LogRedirector(log_path)
    sys.stdout = redirector
    sys.stderr = redirector

    readme = user_documents_dir / "README"
    if not readme.exists():
        try:
            readme.write_text(
                "This folder is used for logging and customising this app."
            )
        except OSError as e:
            print(f"Failed to write placeholder: {e}")

    hot_patch_file = user_documents_dir / "patch_app.py"

    if hot_patch_file.exists():
        print(f"Hot-Patch Intercepted on Device Storage: {hot_patch_file}")
        try:
            sys.path.insert(0, str(user_documents_dir))
            import patch_app  # type: ignore

            print("Hot-patch workspace parsed and executed flawlessly.")
            return patch_app.main()
        except Exception as e: # noqa: BLE001
            print(f"Hot-patch execution runtime failure: {e}")
            print(
                "Gracefully routing application boot back to compiled factory core..."
            )

    print(f"creating MyApp with user_documents_dir: {user_documents_dir}")
    return MyApp(user_documents_dir)


def main() -> toga.App | None:
    """
    Application entry point called by Briefcase or __main__.py.

    :returns: Application instance or None if added to existing event loop.
    :rtype: toga.App | None
    """
    if not (a := toga.App.app):
        return bootstrap_application()
    elif a.loop:
        a.loop.call_soon(cast(Callable[[], None], lambda a=a: MyApp.startup_into(a)))
    else:
        MyApp.startup_into(a)
    return None
