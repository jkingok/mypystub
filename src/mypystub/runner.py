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

from __future__ import annotations

import importlib
import os
import re
import runpy
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, Self

# How a target runs: as a file or module (``python script.py``, ``python -m``),
# or as an entry point of a project's [project.scripts] (cli),
# [project.gui-scripts] (gui) or any other [project.entry-points.<group>]
RunKind = Literal["script", "cli", "gui", "other"]

# PyPA entry point object reference: importable.module[:object.attr][ [extras]]
_IDENTIFIER = r"[^\W\d]\w*"
_REFERENCE = re.compile(
    rf"^\s*(?P<module>{_IDENTIFIER}(?:\.{_IDENTIFIER})*)"
    rf"(?:\s*:\s*(?P<attrs>{_IDENTIFIER}(?:\.{_IDENTIFIER})*))?"
    r"\s*(?:\[[^\]]*\])?\s*$"
)


class NotRunnable(Exception):
    """An entry point names something that can't be called or run."""


class UnsupportedGui(Exception):
    """A GUI entry point starts its own Toga app, which the launcher can't host."""


@dataclass(frozen=True)
class Reference:
    """An entry point's object reference, such as ``pkg.cli:Tool.run``.

    See the PyPA entry points specification. A trailing ``[extras]`` is
    accepted and ignored, as the specification deprecates it.
    """

    module: str
    attrs: tuple[str, ...] = ()

    @classmethod
    def parse(cls, text: str) -> Reference:
        """Parse a reference; ValueError if it isn't one."""
        match = _REFERENCE.match(text)
        if not match:
            raise ValueError(f"Not an entry point reference: {text!r}")
        attrs = match["attrs"]
        return cls(match["module"], tuple(attrs.split(".")) if attrs else ())

    def __str__(self) -> str:
        """The reference without extras, as ``module:attr.attr``."""
        return f"{self.module}:{'.'.join(self.attrs)}" if self.attrs else self.module


def resolve(reference: Reference) -> Any:
    """Import the module, then follow each attribute: classes, methods, values."""
    obj: Any = importlib.import_module(reference.module)
    for attr in reference.attrs:
        obj = getattr(obj, attr)
    return obj


def _toga_app() -> Any:
    """The running Toga app, if Toga has been imported (without importing it)."""
    toga = sys.modules.get("toga")
    app_class = getattr(toga, "App", None)
    return getattr(app_class, "app", None)


def _set_toga_app(app: Any) -> None:
    toga = sys.modules.get("toga")
    if app_class := getattr(toga, "App", None):
        app_class.app = app


def _looks_like_app(obj: object) -> bool:
    return hasattr(obj, "main_loop") and hasattr(obj, "main_window")


class CallAdapter:
    """Run an entry point by calling it with no arguments."""

    def __init__(self, exit_with_result: bool = False) -> None:
        """`exit_with_result`: treat the return value as an exit status.

        Console scripts do: their installed wrapper calls ``sys.exit(main())``.
        """
        self.exit_with_result = exit_with_result

    def call(self, obj: Any, reference: Reference) -> Any:
        """Call `obj`, or say why it can't be run."""
        if not callable(obj):
            kind = type(obj).__name__
            article = "an" if kind[:1].lower() in "aeiou" else "a"
            raise NotRunnable(
                f"{reference} is {article} {kind}, not something that can run."
            )
        result = obj()
        if self.exit_with_result and result is not None:
            raise SystemExit(result)
        return result


class GuiAdapter(CallAdapter):
    """Run a GUI entry point, as far as the launcher can host it.

    Entry points that take over the launcher's window with the takeover
    protocol (``main_window.content_stack``) work. A typical Briefcase
    ``main()`` builds and returns its own ``toga.App`` instead; the launcher
    can't host a second app yet, so that raises :class:`UnsupportedGui`, and
    the launcher's own app is put back if the new one replaced it. Hosting such
    apps on a best-effort basis belongs here.
    """

    def call(self, obj: Any, reference: Reference) -> Any:
        """Call `obj`; refuse, cleanly, if it made its own Toga app."""
        before = _toga_app()
        try:
            result = super().call(obj, reference)
        except NotRunnable:
            raise
        except Exception as e:
            if _toga_app() is not before:
                _set_toga_app(before)
                raise self.unsupported(reference) from e
            raise
        if _toga_app() is not before or (
            _looks_like_app(result) and result is not before
        ):
            _set_toga_app(before)
            raise self.unsupported(reference)
        return result

    @staticmethod
    def unsupported(reference: Reference) -> UnsupportedGui:
        """The error for an entry point that starts its own app."""
        return UnsupportedGui(
            f"{reference} starts its own Toga app, which MyPyStub can't host yet. "
            "GUI entry points can take over the launcher's window instead, with "
            "main_window.content_stack (see the takeover examples)."
        )


ADAPTERS: dict[RunKind, CallAdapter] = {
    "cli": CallAdapter(exit_with_result=True),
    "gui": GuiAdapter(),
    "other": CallAdapter(),
}


@dataclass(frozen=True)
class RunTarget:
    """What to run and where.

    :param path: The entry point file.
    :param import_root: Folder added to ``sys.path`` for the run.
    :param workdir: Working directory for the run.
    :param module: Dotted module name to run with ``python -m`` semantics, or
        None to run ``path`` as a script.
    :param kind: ``"script"`` for files and modules, else the entry point kind.
    :param reference: The entry point's object reference, for entry points.
    :param argv0: ``sys.argv[0]``; an entry point's name, else ``path``.
    """

    path: Path
    import_root: Path
    workdir: Path
    module: str | None = None
    kind: RunKind = "script"
    reference: str | None = None
    argv0: str | None = None


def entry_target(
    name: str, reference: str, kind: RunKind, project_dir: Path, import_root: Path
) -> RunTarget:
    """Build a :class:`RunTarget` for a project's entry point.

    It runs from the project folder with ``import_root`` importable, and
    ``sys.argv[0]`` is the entry point's name, as for an installed script.
    """
    Reference.parse(reference)  # fail early on a malformed reference
    return RunTarget(
        path=Path(project_dir) / "pyproject.toml",
        import_root=Path(import_root),
        workdir=Path(project_dir),
        kind=kind,
        reference=reference,
        argv0=name,
    )


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


class StdinGuard:
    """``sys.stdin`` during a run: closing it closes only this view.

    ``exit()`` and ``quit()`` from :mod:`site` close ``sys.stdin`` before
    raising :class:`SystemExit`, as a terminal would want. In the launcher that
    stream is the app's, and it stays open for later runs. Everything else is
    passed through to the real stream.
    """

    def __init__(self, stream: Any) -> None:
        """Wrap `stream`, the app's own ``sys.stdin``."""
        self._stream = stream
        self._closed = False

    def close(self) -> None:
        """Close this view; the app's stream stays open."""
        self._closed = True

    @property
    def closed(self) -> bool:
        """Whether this view, or the stream under it, is closed."""
        return self._closed or bool(self._stream.closed)

    def _check(self) -> None:
        if self._closed:
            raise ValueError("I/O operation on closed file.")

    def read(self, *args: Any) -> str:
        """Read from the stream, unless this view is closed."""
        self._check()
        return self._stream.read(*args)

    def readline(self, *args: Any) -> str:
        """Read a line from the stream, unless this view is closed."""
        self._check()
        return self._stream.readline(*args)

    def readlines(self, *args: Any) -> list[str]:
        """Read lines from the stream, unless this view is closed."""
        self._check()
        return self._stream.readlines(*args)

    def __iter__(self) -> Any:
        """Iterate over lines, unless this view is closed."""
        self._check()
        return iter(self._stream)

    def __getattr__(self, name: str) -> Any:
        """Everything else (fileno, encoding, isatty...) is the stream's."""
        return getattr(self._stream, name)


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
        self.argv = [target.argv0 or str(target.path), *argv]
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
            "stdin": sys.stdin,
        }
        if sys.stdin is not None:
            sys.stdin = StdinGuard(sys.stdin)  # type: ignore[assignment]
        sys.argv = list(self.argv)
        os.environ.update(self.env)
        os.chdir(self.target.workdir)
        sys.path.insert(0, str(self.target.import_root))
        return self

    def run(self) -> dict[str, Any]:
        """Execute the target as ``__main__`` and return its globals.

        An entry point that names only a module runs it like ``python -m``.
        One that names an object is resolved, attribute by attribute, and
        called by its kind's adapter; its return value is in ``"result"``.
        """
        if self.target.reference:
            reference = Reference.parse(self.target.reference)
            if not reference.attrs:
                return runpy.run_module(
                    reference.module, run_name="__main__", alter_sys=True
                )
            obj = resolve(reference)
            adapter = ADAPTERS.get(self.target.kind, ADAPTERS["other"])
            return {"result": adapter.call(obj, reference)}
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
        sys.stdin = saved["stdin"]
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
