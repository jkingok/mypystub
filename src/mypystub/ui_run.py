"""Running a prototype: start it, watch it end, and handle row taps."""

from __future__ import annotations

import asyncio
import dataclasses
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import toga

from . import piplike as pip
from . import (
    row_info,
    runner,
    scan,
    webapps,
    workdirs,
)
from .errors import guarded
from .run_settings import quick_start_name
from .run_status import (  # noqa: F401  (re-exported for callers and tests)
    DEPENDENCY_FAILED,
    FINISHED,
    LOAD_FAILED,
    STOPPED,
    run_status,
)
from .ui_base import RUNNING
from .ui_native import NativeMixin


class RunMixin(NativeMixin):
    """Running a prototype and noticing when its run ends."""

    def __init__(self, host_app: toga.App, on_done: Callable[[Any], None]) -> None:
        super().__init__(host_app, on_done)
        # Each run gets an id; end-of-run work for an older run is ignored (#64)
        self.run_id = 0
        self.ended_run = 0
        # A run is in progress from run_row until end_script (#301): one at a
        # time, since runs share the process's streams, hooks and Script tab
        self.running = False
        self.script_list.on_select = self.handle_row_selection

    def end_script(self, run_id: int | None = None, status: str = FINISHED) -> None:
        """Tidy up after a run: back to the list unless there's output to read.

        The activity row keeps `status`, how the run ended (see run_status),
        whether the tab stays or not, so it's there to read when the Script
        tab is next opened. Tabs only change while the launcher is on screen;
        if a takeover is still showing, they're left alone (#64, case C).
        """
        self.splash.image = None
        self.running = False
        self.title_prefix = ""  # the run is over: the title loses ⏳/⌨️ (#306)
        if watch := getattr(self, "_takeover_watch", None):
            watch[0].remove_listener(watch[1])
            self._takeover_watch = None
        self.script_activity.style.display = "pack"
        self.script_activity.update(status, on=False)
        action = runner.end_action(printed=self.script_runner.printed, error=False)
        if action != "stay" and self.tabs.window is not None:
            self.tabs.current_tab = "List"
        self.ended_run = self.run_id if run_id is None else run_id
        # The script may have retitled the window, with or without a takeover
        self.apply_window_title()

    def start(self, context: runner.RunContext) -> None:
        """Run a prototype on the script thread, like ``python script.py``.

        The run ends when the body returns, or, if it took over the window, when
        its takeover is popped off the content stack (see runner.RunLifetime).
        """
        print("Starting...")
        self.run_id += 1
        run_id = self.run_id
        stack = self.content_stack()
        # A takeover's extra Back can't pop below the launcher (#64, case E)
        stack.floor = len(stack)
        lifetime = runner.RunLifetime(
            stack,
            self.app.loop.call_soon_threadsafe,
            lambda error: self.finish_run(context, error, run_id),
        )
        self.run_lifetime = lifetime
        self.run_took_over = False
        start_depth = len(stack)

        def note_takeover(depth: int) -> None:
            if depth > start_depth:
                self.run_took_over = True  # stays so after the pop (#306)
                stack.remove_listener(note_takeover)

        stack.add_listener(note_takeover)
        self._takeover_watch = (stack, note_takeover)
        if self.script_runner.console is not None:
            # The Experimental Console's ⏳ (#306) says it's running, so the
            # activity row is redundant until the run ends, and would only take
            # height above the keyboard
            self.set_title_prefix(RUNNING)
            self.script_activity.style.display = "none"
        self.script_runner.begin_run()
        context.open()

        def script() -> None:
            error: BaseException | None = None
            try:
                context.run()
            except SystemExit as e:
                # sys.exit() / sys.exit(0) is a normal end, like at the terminal
                if e.code not in (None, 0):
                    error = e
            except BaseException as e:  # noqa: BLE001
                error = e
            finally:
                lifetime.body_finished(error)

        self.script_runner.run_student_script(script)

    def finish_run(
        self,
        context: runner.RunContext,
        error: BaseException | None,
        run_id: int | None = None,
    ) -> None:
        """Restore process state, report any error, and tidy up the Script tab.

        Runs once per run, on the loop (runner.RunLifetime). If a newer run has
        started meanwhile, only the process state is restored (#64, case G).
        """
        context.close()
        run_id = self.run_id if run_id is None else run_id
        if run_id != self.run_id:
            print(f"Run {run_id} ended after run {self.run_id} started; ignored")
            return
        self.script_runner.end_run()
        if self.console_widget is not None:
            # The console is read-only again; put its keyboard away too
            self.close_keyboard(self.console_widget)
        self.resume_running = None  # it ended, so there is nothing to offer again
        self.remember()
        status = run_status(error)
        if error is None:
            self.end_script(run_id, status)
            return
        traceback.print_exception(error)
        self.script_activity.update(status, on=False)

        async def report() -> None:
            title = "Script Failure"
            if isinstance(error, (runner.NotRunnable, runner.UnsupportedGui)):
                message, title = str(error), "Can't Run"
            elif isinstance(error, SystemExit):
                message = f"Script exited with status {error.code}"
            else:
                message = f"Script failed with: {error!s}"
            await self.error(message, title)
            if run_id == self.run_id:
                self.end_script(run_id, status)

        asyncio.create_task(report())

    @guarded
    async def handle_row_selection(
        self, widget: toga.DetailedList, **kwargs: Any
    ) -> None:
        """Triggered automatically when an iOS row is tapped."""
        # Grab the currently selected row data dictionary
        selected_row = widget.selection
        self.clear_selection(widget)
        if selected_row is None:
            return

        # Category rows, and ".." back to them, navigate instead of running
        if getattr(selected_row, "categories", False):
            self.show_category(None)
            self.reload_menu(widget)
            return
        if category := getattr(selected_row, "category", None):
            self.show_category(category)
            self.reload_menu(widget)
            return

        # Packages with several entry points open like folders
        if getattr(selected_row, "package_up", False):
            self.package_dir = None
            self.reload_menu(widget)
            return
        if row_info.row_type(selected_row) == "package":
            self.package_dir = Path(cast(Any, selected_row).project_dir)
            self.reload_menu(widget)
            return

        # Folder rows (including "..") navigate instead of running anything
        if folder := getattr(selected_row, "folder", None):
            self.subfolder = scan.relative_folder(self.get_category_dir(), folder)
            self.reload_menu(widget)
            return

        if row_info.row_type(selected_row) == "web":
            self.open_web_app(selected_row)
            return

        if not row_info.runnable(row_info.row_type(selected_row)):
            return
        await self.run_row(selected_row)

    def open_web_app(self, row: Any) -> None:
        """Serve a web app from 127.0.0.1 and show it over the launcher.

        Back stops the server. Links to other sites open in the browser; only
        the app's own pages load in the view.
        """
        try:
            server = webapps.StaticServer(Path(row.web_root), str(row.web_page))
            url = server.start()
        except OSError as error:
            asyncio.create_task(
                self.error(f"Couldn't start the web app: {error}", "Web")
            )
            return

        @guarded
        def navigate(widget: toga.WebView, url: str, **kwargs: Any) -> bool:
            if url.startswith("http://127.0.0.1:"):
                return True
            return self.open_external(widget, url=url)

        def back(widget: toga.Widget | None = None, **kwargs: Any) -> None:
            server.stop()
            self.pop_screen()

        view = toga.WebView(url=url, flex=1, on_navigation_starting=navigate)
        top = toga.Row(children=[toga.Button("‹ Back", on_press=guarded(back))])
        self.push_screen(
            str(row.title), toga.Column(children=[top, view]), on_back=back
        )

    @guarded
    async def offer_quick_start(self) -> None:
        """At launch, ask whether to run the saved Quick Start, then run it.

        Does nothing if no Quick Start is set, or it names a target that is no
        longer there (resolve_quick_start clears a stale setting).
        """
        row = self.resolve_quick_start()
        if row is None:
            return
        name = quick_start_name(self.settings.get_quick_start() or "")
        if await self.ask("Quick Start", f"Do you want to run {name}?"):
            self.open_quick_start_folder()
            self.reload_menu(self.script_list)
            await self.run_row(row)

    @guarded
    async def run_row(self, selected_row: Any) -> None:
        """Run a script or project row with the settings saved in its Setup.

        Only one at a time (#301): while a run is in progress, from here until
        end_script (a takeover counts until it's popped), another is refused
        with an alert, and the Script tab is shown.
        """
        if self.running:
            if self.tabs.window is not None:
                self.tabs.current_tab = "Script"
            await self.info("Another script is already running.", "Already running")
            return
        self.running = True
        try:
            await self._run_row(selected_row)
        except BaseException:
            self.running = False  # never leave the app unable to run anything
            raise

    async def _run_row(self, selected_row: Any) -> None:
        """run_row's work, once it's clear nothing else is running."""
        settings, env = self.run_settings_for(selected_row)

        # 1. Read the parsed dependency requirements array
        required_packages = getattr(selected_row, "dependencies", [])

        target_user_packages = self.cache_path / "site_packages"
        # The folder must exist before the run puts it on sys.path, or imports
        # searching it cache "nothing here" (piplike also clears that after
        # installing). RunContext adds it to the path only for the run and
        # takes it off again, so the launcher never imports from it.
        target_user_packages.mkdir(parents=True, exist_ok=True)

        # Switch to the Script view first, so installing dependencies shows
        # progress there instead of leaving the list looking frozen.
        title = getattr(selected_row, "title", "script")
        self.run_title = str(title)
        self.choose_output()  # Experimental Console or not, and emptied
        self.error_text.value = ""
        self.hide_errors()
        # Only a prototype's own icon is shown as a splash, never a default one
        if splash := getattr(selected_row, "splash", None):
            self.splash.image = splash
            self.splash.style.flex = 1
            self.script_output.style.flex = 0
        else:
            self.splash.image = None
            self.splash.style.flex = 0
            self.script_output.style.flex = 1
        self.tabs.current_tab = "Script"
        self.script_activity.update(f"Preparing {title}")

        # On a desktop, Native mode uses pip and a subprocess instead (#280)
        if self.native_mode:
            await self.run_native(selected_row, list(settings.args), env, str(title))
            return

        # 2. Check and satisfy dependencies
        if required_packages:
            # TODO Insert cache dir
            try:
                await pip.resolve_and_install_async(
                    required_packages,
                    target_user_packages,
                    on_progress=self.script_activity.update,
                    aliases={
                        **self.configured_aliases(),
                        **(getattr(selected_row, "aliases", None) or {}),
                    },
                )
            except Exception as e:  # noqa: BLE001
                # DependencyError, or e.g. an invalid requirement string
                traceback.print_exc()
                self.script_activity.update(DEPENDENCY_FAILED, on=False)
                await self.error(str(e), "Dependency Error")
                self.end_script(status=DEPENDENCY_FAILED)
                return

        # 3. Run it the way Python would: __main__, argv, its folder importable
        try:
            context = runner.RunContext(
                self.run_target(selected_row),
                argv=settings.args,
                env=env,
                user_site=target_user_packages,
            )
        except Exception as e:  # noqa: BLE001
            self.script_activity.update(LOAD_FAILED, on=False)
            await self.error(f"Failed to execute script:\n{e!s}", "Load Failure")
            self.end_script(status=LOAD_FAILED)
            return

        self.script_activity.update(self.running_text(str(title)))
        try:
            # If the app is ended while this runs, the next launch offers it again
            self.resume_running = (self.row_key(selected_row), str(title))
        except (AssertionError, ValueError):
            self.resume_running = None
        self.remember()
        self.app.loop.call_soon(lambda: self.start(context))

    def run_target(self, row: Any) -> runner.RunTarget:
        """What a runnable row runs, working in its chosen folder (#308)."""
        target = self.code_target(row)
        choice = self.workdir_for(row)
        folder, notice = workdirs.resolve(
            choice,
            script_folder=target.workdir,
            cache=Path(self.cache_path),
            documents_root=self.category_dirs()["Documents"],
            key=self.row_key(row),
        )
        if notice:
            asyncio.ensure_future(self.info(notice, "Working folder"))
        self.run_workdir = workdirs.describe(choice) if folder != target.workdir else ""
        return dataclasses.replace(target, workdir=folder)

    def running_text(self, title: str) -> str:
        """The activity row while a run goes: where it works, if not its own folder."""
        where = getattr(self, "run_workdir", "")
        return f"Running {title} · in {where}" if where else f"Running {title}"

    def code_target(self, row: Any) -> runner.RunTarget:
        """What a runnable row runs: a file, or one of its project's entry points."""
        if entry := getattr(row, "entry", None):
            project_dir = Path(row.project_dir)
            folder_root = Path(getattr(row, "folder_root", project_dir))
            print(f"Launching {entry.name} ({entry.reference}) from {project_dir}")
            return runner.entry_target(
                entry.name, entry.reference, entry.kind, project_dir, folder_root
            )
        entry_point = Path(row.entry_point)
        folder_root = Path(getattr(row, "folder_root", entry_point.parent))
        print(f"Launching {row.title} from path: {entry_point}")
        if not entry_point.is_file():
            raise FileNotFoundError(f"Entry point not found: {entry_point}")
        return runner.target_for(entry_point, folder_root)
