"""Native mode's runs: pip into the managed venv, then a subprocess (#280).

Only on desktops (see native.py). The Script tab works as it does for an
in-process run: progress while preparing, the prototype's output and errors as
they're written, and the input field, which here writes a line to the
prototype's stdin (and echoes it, as a terminal would). A Toga prototype opens
its own window; the run ends when its process does.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Callable, Mapping
from typing import Any

import toga

from . import native
from .errors import guarded
from .run_settings import EnvValue
from .run_status import DEPENDENCY_FAILED, STOPPED, exit_status
from .ui_rowsettings import RowSettingsMixin

log = logging.getLogger(__name__)

EOT_BYTE, ETX_BYTE = b"\x04", b"\x03"  # Ctrl-D and Ctrl-C, from the console
CHUNK = 4096  # read output in pieces, not lines: input() prompts have no newline
STOP_GRACE = 3.0  # seconds between asking a stopped process to end and killing it


class NativeMixin(RowSettingsMixin):
    """Running prototypes with the real Python tools on a desktop."""

    def __init__(self, host_app: toga.App, on_done: Callable[[Any], None]) -> None:
        super().__init__(host_app, on_done)
        self.native_process: asyncio.subprocess.Process | None = None
        self.native_stopped = False
        # Shown beside the Script tab's activity while a subprocess runs
        self.stop_button = toga.Button(
            "Stop", on_press=self.handle_stop, visibility="hidden"
        )
        # At the end of the activity row, which input()'s question swaps out
        self.script_activity.add(self.stop_button)

    @property
    def native_cache(self) -> Any:
        """Where the managed venv lives: the app's cache."""
        return self.cache_path

    async def run_native(
        self, row: Any, argv: list[str], env: Mapping[str, EnvValue], title: str
    ) -> None:
        """Install `row`'s dependencies with pip, then run it in a subprocess."""
        target = self.run_target(row)  # type: ignore[attr-defined]  (RunMixin)
        self.native_stopped = False
        try:
            self.script_activity.update("Preparing Python")
            python = await asyncio.to_thread(native.ensure_venv, self.native_cache)
            if requirements := list(getattr(row, "dependencies", []) or []):
                self.script_activity.update("Installing with pip")
                code = await self.stream(native.pip_command(python, requirements))
                if self.native_stopped:
                    self.end_script(status=STOPPED)  # type: ignore[attr-defined]
                    return
                if code != 0:
                    raise RuntimeError(
                        f"pip couldn't install {', '.join(requirements)}"
                    )
        except Exception as error:  # noqa: BLE001  (shown, then back to the list)
            self.script_activity.update(DEPENDENCY_FAILED, on=False)
            await self.error(str(error), "Dependency Error")
            self.end_script(status=DEPENDENCY_FAILED)  # type: ignore[attr-defined]
            return
        self.script_activity.update(self.running_text(title))  # type: ignore[attr-defined]
        self.run_id += 1  # type: ignore[has-type]
        run_id = self.run_id
        code = await self.stream(
            native.run_command(python, target, argv),
            cwd=str(target.workdir),
            env=native.run_environment(target, env),
            interactive=True,
        )
        if run_id != self.run_id:
            return
        # The status row keeps how it ended, as for an in-process run (#293)
        if self.native_stopped:
            self.end_script(run_id, status=STOPPED)  # type: ignore[attr-defined]
            return
        status = exit_status(code)
        if code == 0:
            self.end_script(run_id, status=status)  # type: ignore[attr-defined]
            return
        self.script_activity.update(status, on=False)
        await self.error(f"Script exited with status {code}", "Script Failure")
        if run_id == self.run_id:
            self.end_script(run_id, status=status)  # type: ignore[attr-defined]

    async def stream(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        interactive: bool = False,
    ) -> int:
        """Run `command`, its output going to the Script tab; its exit code.

        With `interactive`, the input field stays up and sends lines to stdin.
        """
        log.debug(f"Native: {' '.join(command[:4])} …")
        self.script_runner.begin_run()
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd,
            env=env,
            stdin=asyncio.subprocess.PIPE
            if interactive
            else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self.native_process = process
        self.stop_button.style.visibility = "visible"
        if interactive:
            self.offer_stdin(process)
        try:
            await asyncio.gather(
                self.pump(process.stdout, error=False),
                self.pump(process.stderr, error=True),
            )
            return await process.wait()
        finally:
            self.native_process = None
            self.stop_button.style.visibility = "hidden"
            if interactive:
                self.withdraw_stdin()
            self.script_runner.end_run()

    @guarded
    async def handle_stop(
        self, widget: toga.Widget | None = None, **kwargs: Any
    ) -> None:
        """Stop the running subprocess: ask it to end, then kill it if it won't."""
        process = self.native_process
        if process is None or process.returncode is not None:
            return
        self.native_stopped = True
        self.script_activity.update("Stopping")
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), STOP_GRACE)
        except TimeoutError:
            process.kill()

    async def pump(self, source: asyncio.StreamReader | None, error: bool) -> None:
        """Copy a pipe to the log and the Script tab as it arrives."""
        if source is None:
            return
        while chunk := await source.read(CHUNK):
            self.show_native(chunk.decode("utf-8", errors="replace"), error)

    def show_native(self, text: str, error: bool = False) -> None:
        """Show the subprocess's text, as a prototype's own output is shown.

        Launcher code writing to sys.stdout only reaches the log (hooks'
        RunStream), so the log gets it directly and the Script tab through the
        runner, as an echoed input() answer does.
        """
        self.script_runner.log_only(text, error)
        if error:
            self.script_runner.append_error(text)
        else:
            self.script_runner.append_to_log(text)

    def offer_stdin(self, process: asyncio.subprocess.Process) -> None:
        """Let the user type to `process`'s stdin.

        With the Experimental Console, the console itself: each line typed
        goes to stdin (the console echoes it), Ctrl-D closes stdin and Ctrl-C
        interrupts the process, as at a terminal. Otherwise the input field,
        whose Return sends its text, echoed into the output.
        """
        console = self.script_runner.console
        if console is not None:

            def typed(widget: Any, data: bytes, **kwargs: Any) -> None:
                stdin = process.stdin
                if stdin is None or process.returncode is not None:
                    return
                if data == EOT_BYTE:
                    stdin.close()
                elif data == ETX_BYTE:
                    interrupt(process)
                else:
                    stdin.write(data)
                    self.script_runner.log_only(data.decode("utf-8", "replace"))

            console.on_input = typed
            console.readonly = False
            return
        field = self.input_text
        self.native_saved_confirm = field.on_confirm
        self.input_prompt.text = "Input"

        def send(widget: toga.TextInput, **kwargs: Any) -> None:
            line = str(widget.value)
            widget.value = ""
            self.show_native(line + "\n")  # echoed, as a terminal would
            if process.stdin is not None and process.returncode is None:
                process.stdin.write((line + "\n").encode("utf-8"))

        field.on_confirm = send
        self.toggle_input(True)

    def withdraw_stdin(self) -> None:
        """Stop sending typing to the process."""
        console = self.script_runner.console
        if console is not None:
            console.on_input = None
            console.readonly = True
            return
        self.toggle_input(False)
        self.input_text.on_confirm = self.native_saved_confirm


def interrupt(process: asyncio.subprocess.Process) -> None:
    """Ctrl-C for a subprocess: SIGINT, or Windows' console equivalent."""
    import signal

    if sys.platform == "win32":
        process.send_signal(signal.CTRL_C_EVENT)  # pyright: ignore[reportAttributeAccessIssue]
    else:
        process.send_signal(signal.SIGINT)
