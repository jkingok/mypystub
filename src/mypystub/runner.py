"""Run prototypes the way Python does, and know when a run has ended.

Kept free of Toga imports so it can be unit tested on desktop.

- :class:`RunContext` sets ``sys.argv``, the environment, the working directory
  and ``sys.path`` for one run, executes the target with :mod:`runpy` (so
  ``if __name__ == "__main__":`` works), and restores everything afterwards.
- :class:`RunLifetime` decides when the run is over. A plain script is over when
  its body returns. A takeover (a script that pushes its own UI onto the
  window's ``content_stack``) is over when the stack shrinks back to where it
  started, which is when its Back/done callback pops it.
"""

import os
import runpy
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Self


@dataclass(frozen=True)
class RunTarget:
    """What to run and where.

    :param path: The entry point file.
    :param import_root: Folder added to ``sys.path`` for the run.
    :param workdir: Working directory for the run.
    :param module: Dotted module name to run with ``python -m`` semantics, or
        None to run ``path`` as a script.
    """

    path: Path
    import_root: Path
    workdir: Path
    module: str | None = None


def target_for(entry_point: Path, folder_root: Path) -> RunTarget:
    """Build a :class:`RunTarget` from a scanned prototype entry.

    An entry point inside a package under ``folder_root`` runs the way
    ``python -m`` would, so relative imports work: ``src/pkg/__main__.py`` as
    ``python -m pkg`` and ``src/pkg/app.py`` as ``python -m pkg.app``. The
    working directory is then the project folder (the parent of ``src/``).
    Anything else runs as a script from its own folder, like
    ``python script.py``.
    """
    entry_point, folder_root = Path(entry_point), Path(folder_root)
    package_dir = entry_point.parent
    if (
        (package_dir / "__init__.py").is_file()
        and package_dir.is_relative_to(folder_root)
        and package_dir != folder_root
    ):
        parts = list(entry_point.relative_to(folder_root).with_suffix("").parts)
        if parts[-1] == "__main__":
            parts.pop()  # run the package itself, which executes __main__
        workdir = folder_root.parent if folder_root.name == "src" else folder_root
        return RunTarget(entry_point, folder_root, workdir, ".".join(parts))
    return RunTarget(entry_point, folder_root, entry_point.parent)


class RunContext:
    """Process state for one run, applied on :meth:`open` and undone on :meth:`close`.

    Modules first imported during the run are removed on close only if they were
    loaded from ``purge_roots`` (by default the run's import root). That makes
    edits to a prototype take effect on the next run, while leaving Toga and the
    standard library alone: the app already holds references to those, and a
    second copy would mix versions.
    """

    def __init__(
        self,
        target: RunTarget,
        argv: Sequence[str] = (),
        env: Mapping[str, str] | None = None,
        purge_roots: Iterable[Path] = (),
    ) -> None:
        """Prepare a run of `target` with extra `argv` and `env` entries."""
        self.target = target
        self.argv = [str(target.path), *argv]
        self.env = dict(env or {})
        self.purge_roots = [p.resolve() for p in (target.import_root, *purge_roots)]
        self._saved: dict[str, Any] | None = None

    def open(self) -> Self:
        """Snapshot the process state and apply this run's settings."""
        if self._saved is not None:
            return self
        self._saved = {
            "argv": list(sys.argv),
            "environ": dict(os.environ),
            "cwd": os.getcwd(),
            "path": list(sys.path),
            "modules": set(sys.modules),
        }
        sys.argv = list(self.argv)
        os.environ.update(self.env)
        os.chdir(self.target.workdir)
        sys.path.insert(0, str(self.target.import_root))
        return self

    def run(self) -> dict[str, Any]:
        """Execute the target as ``__main__`` and return its globals."""
        if self.target.module:
            return runpy.run_module(
                self.target.module, run_name="__main__", alter_sys=True
            )
        return runpy.run_path(str(self.target.path), run_name="__main__")

    def close(self) -> None:
        """Restore the snapshot. Safe to call more than once."""
        if self._saved is None:
            return
        saved, self._saved = self._saved, None
        sys.argv = saved["argv"]
        os.environ.clear()
        os.environ.update(saved["environ"])
        os.chdir(saved["cwd"])
        sys.path[:] = saved["path"]
        for name in set(sys.modules) - saved["modules"]:
            if self._from_purge_roots(sys.modules.get(name)):
                del sys.modules[name]

    def _from_purge_roots(self, module: object) -> bool:
        """Whether `module` was loaded from one of the purge roots."""
        file = getattr(module, "__file__", None)
        if not file:
            return False
        path = Path(file).resolve()
        return any(path.is_relative_to(root) for root in self.purge_roots)

    def __enter__(self) -> Self:
        """Open the context."""
        return self.open()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the context, even when the run raised."""
        self.close()


def end_action(printed: bool, error: bool) -> str:
    """What the Script tab does when a run ends (#64).

    ``"list"``: go back to the list, because there's nothing left to read.
    ``"stay"``: stay on the Script tab to show the output. An error's dialog is
    shown first either way.
    """
    del error  # the dialog has been dismissed by the time this applies
    return "stay" if printed else "list"


class ObservableStack(list):
    """A list that tells listeners its new length after every push or pop.

    The launcher installs this as ``main_window.content_stack``, so it can see a
    takeover start (push) and end (pop) without polling.

    ``floor`` guards against extra pops (#64, case E): a pop that would go below
    it is ignored, and returns the window's current title and content, so the
    caller restores what's already showing. Without a ``window`` it raises
    IndexError, like popping an empty list.
    """

    def __init__(self, *args: Any) -> None:
        """Create the stack, optionally from an existing list."""
        super().__init__(*args)
        self._listeners: list[Callable[[int], None]] = []
        self.floor = 0
        self.window: Any = None

    def add_listener(self, listener: Callable[[int], None]) -> None:
        """Call `listener(len(self))` after each change."""
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[int], None]) -> None:
        """Stop calling `listener`."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _changed(self) -> None:
        for listener in list(self._listeners):
            listener(len(self))

    def append(self, item: Any) -> None:
        """Push `item` and notify listeners."""
        super().append(item)
        self._changed()

    def pop(self, index: Any = -1) -> Any:
        """Pop an item and notify listeners; ignore pops below the floor."""
        if len(self) <= self.floor:
            if self.window is None:
                raise IndexError("pop below the content stack's floor")
            print("[Launcher] Ignored an extra pop of the content stack")
            return (self.window.title, self.window.content)
        item = super().pop(index)
        self._changed()
        return item


class RunLifetime:
    """Decides when a run ends: when its body returns, or when its takeover pops.

    :param stack: The window's content stack.
    :param call_soon_threadsafe: The app loop's ``call_soon_threadsafe``.
    :param on_finished: Called once, on the loop, with the body's exception or
        None.
    """

    def __init__(
        self,
        stack: ObservableStack,
        call_soon_threadsafe: Callable[..., Any],
        on_finished: Callable[[BaseException | None], None],
    ) -> None:
        """Record the stack depth at the start of the run."""
        self.stack = stack
        self.start_depth = len(stack)
        self.call_soon_threadsafe = call_soon_threadsafe
        self.on_finished = on_finished
        self.took_over = False
        self.error: BaseException | None = None
        self._body_done = False
        self._finished = False

    def body_finished(self, error: BaseException | None = None) -> None:
        """Report that the script body returned or raised. Any thread may call this.

        The check is queued on the loop rather than done now: a takeover may have
        queued its push with ``loop.call_soon`` just before returning, and a
        callback queued after it sees the final depth.
        """
        if self._body_done:
            return
        self._body_done = True
        self.error = error
        self.call_soon_threadsafe(self._check)

    def _check(self) -> None:
        if len(self.stack) > self.start_depth:
            self.took_over = True
            self.stack.add_listener(self._on_stack_change)
        else:
            self._finish()

    def _on_stack_change(self, depth: int) -> None:
        # Any thread may pop (case D). Finish on the loop, after the pop and the
        # content it restores have completed (case F).
        if depth <= self.start_depth:
            self.call_soon_threadsafe(self._finish)

    def _finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        self.stack.remove_listener(self._on_stack_change)
        self.on_finished(self.error)
