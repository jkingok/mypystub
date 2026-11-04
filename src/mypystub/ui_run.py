"""Running a prototype: start it, watch it end, and handle row taps."""

from __future__ import annotations

import asyncio
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
)
from .run_settings import quick_start_name
from .ui_rowsettings import RowSettingsMixin


class RunMixin(RowSettingsMixin):
    """Running a prototype and noticing when its run ends."""

    def __init__(self, host_app: toga.App, on_done: Callable[[Any], None]) -> None:
        super().__init__(host_app, on_done)
        # Each run gets an id; end-of-run work for an older run is ignored (#64)
        self.run_id = 0
        self.ended_run = 0
        self.script_list.on_select = self.handle_row_selection

    def end_script(self, run_id: int | None = None) -> None:
        """Tidy up after a run: back to the list unless there's output to read.

        Tabs only change while the launcher is on screen; if a takeover is still
        showing, they're left alone (#64, case C).
        """
        self.splash.image = None
        action = runner.end_action(printed=self.script_runner.printed, error=False)
        if action == "stay":
            self.script_activity.update("Finished", on=False)
        else:
            self.script_activity.update(on=False)
            if self.tabs.window is not None:
                self.tabs.current_tab = "List"
        self.ended_run = self.run_id if run_id is None else run_id

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
        if error is None:
            self.end_script(run_id)
            return
        traceback.print_exception(error)
        self.script_activity.update("Failed", on=False)

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
                self.end_script(run_id)

        asyncio.create_task(report())

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

        if not row_info.runnable(row_info.row_type(selected_row)):
            return
        await self.run_row(selected_row)

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

    async def run_row(self, selected_row: Any) -> None:
        """Run a script or project row with the settings saved in its Setup."""
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
        self.print_text.value = ""
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
        self.app.widgets["tabs"].current_tab = "Script"
        self.script_activity.update(f"Preparing {title}")

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
                self.script_activity.update("Dependency install failed", on=False)
                await self.error(str(e), "Dependency Error")
                self.end_script()
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
            self.script_activity.update(on=False)
            await self.error(f"Failed to execute script:\n{e!s}", "Load Failure")
            self.end_script()
            return

        self.script_activity.update(f"Running {title}")
        self.app.loop.call_soon(lambda: self.start(context))

    def run_target(self, row: Any) -> runner.RunTarget:
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
