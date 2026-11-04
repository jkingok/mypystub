"""Tests for running prototypes the way Python does (mypystub.runner, #57)."""

import io
import os
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from mypystub.runner import (
    NotRunnable,
    ObservableStack,
    Reference,
    RunContext,
    RunLifetime,
    UnsupportedGui,
    end_action,
    entry_target,
    resolve,
    target_for,
)


def write(path: Path, text: str) -> Path:
    """Create `path` with `text`, making parent folders as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """A module scripts can report into, standing in for the launcher's state."""
    module = ModuleType("runner_registry")
    module.items = []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "runner_registry", module)
    return module


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------


def test_target_for_script(tmp_path: Path) -> None:
    """A loose script runs by path, with its folder importable and as cwd."""
    script = write(tmp_path / "s.py", "")
    target = target_for(script, tmp_path)
    assert (target.path, target.module, target.import_root) == (script, None, tmp_path)
    assert target.workdir == tmp_path


def test_target_for_project_package(tmp_path: Path) -> None:
    """A project's src/<pkg>/__main__.py runs as `python -m pkg`."""
    entry = write(tmp_path / "proj" / "src" / "pkg" / "__main__.py", "")
    write(tmp_path / "proj" / "src" / "pkg" / "__init__.py", "")
    target = target_for(entry, tmp_path / "proj" / "src")
    assert target.module == "pkg"
    assert target.workdir == tmp_path / "proj"


def test_target_for_module_inside_a_package(tmp_path: Path) -> None:
    """Any entry point inside a package runs as `python -m pkg.module`."""
    src = tmp_path / "proj" / "src"
    write(src / "pkg" / "__init__.py", "")
    write(src / "pkg" / "sub" / "__init__.py", "")
    app = write(src / "pkg" / "app.py", "")
    tool = write(src / "pkg" / "sub" / "tool.py", "")
    assert target_for(app, src).module == "pkg.app"
    assert target_for(tool, src).module == "pkg.sub.tool"
    assert target_for(app, src).workdir == tmp_path / "proj"


def test_loose_file_beside_a_package_stays_a_script(tmp_path: Path) -> None:
    """A .py directly in the import root is not in a package: run it by path."""
    write(tmp_path / "pkg" / "__init__.py", "")
    script = write(tmp_path / "main.py", "")
    assert target_for(script, tmp_path).module is None


# ---------------------------------------------------------------------------
# RunContext
# ---------------------------------------------------------------------------


def test_main_guard_runs_with_script_argv(tmp_path: Path, registry: ModuleType) -> None:
    """`if __name__ == "__main__"` runs, and argv[0] is the script path."""
    script = write(
        tmp_path / "s.py",
        "import sys, runner_registry\n"
        "if __name__ == '__main__':\n"
        "    runner_registry.items.append(list(sys.argv))\n",
    )
    with RunContext(target_for(script, tmp_path), argv=["--fast", "x"]) as run:
        run.run()
    assert registry.items == [[str(script), "--fast", "x"]]


def test_state_is_applied_then_restored(
    tmp_path: Path, registry: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """argv, environment (added and removed keys), cwd and sys.path come back."""
    monkeypatch.setenv("KEEP_ME", "1")
    monkeypatch.setenv("REMOVE_ME", "1")
    script = write(
        tmp_path / "s.py",
        "import os, sys, runner_registry\n"
        "runner_registry.items.append((os.environ.get('GREETING'), os.getcwd()))\n"
        "os.environ.pop('REMOVE_ME')\n"
        "os.environ['LEAKED'] = 'x'\n",
    )
    before = (list(sys.argv), dict(os.environ), os.getcwd(), list(sys.path))
    with RunContext(target_for(script, tmp_path), env={"GREETING": "hi"}) as run:
        run.run()
    assert registry.items == [("hi", str(tmp_path))]
    assert (list(sys.argv), dict(os.environ), os.getcwd(), list(sys.path)) == before


def test_run_modules_are_cleared_but_framework_modules_kept(
    tmp_path: Path, registry: ModuleType
) -> None:
    """The script's own modules are dropped; stdlib imports made during it stay."""
    write(tmp_path / "helper_for_runner_test.py", "VALUE = 1\n")
    script = write(
        tmp_path / "s.py",
        "import helper_for_runner_test, colorsys\n",
    )
    sys.modules.pop("colorsys", None)
    with RunContext(target_for(script, tmp_path)) as run:
        run.run()
    assert "helper_for_runner_test" not in sys.modules
    assert "colorsys" in sys.modules


def test_user_site_is_scoped_to_the_run(tmp_path: Path) -> None:
    """user_site is on sys.path for the run and off it after, and a module
    imported from it is purged, so the launcher never inherits a script's
    packages (the shared folder stays on disk for the next run)."""
    site = tmp_path / "site"
    write(site / "user_pkg_for_runner_test.py", "VALUE = 1\n")
    script = write(tmp_path / "s.py", "import user_pkg_for_runner_test\n")
    sys.modules.pop("user_pkg_for_runner_test", None)
    before = list(sys.path)
    with RunContext(target_for(script, tmp_path), user_site=site) as run:
        run.run()  # the import only resolves because user_site is on the path
    assert str(site) not in sys.path
    assert sys.path == before
    assert "user_pkg_for_runner_test" not in sys.modules


def test_callbacks_keep_their_globals(tmp_path: Path, registry: ModuleType) -> None:
    """Functions the script hands to the app still work after run_path returns."""
    script = write(
        tmp_path / "s.py",
        "import runner_registry\n"
        "GREETING = 'still here'\n"
        "def callback():\n"
        "    return GREETING\n"
        "runner_registry.items.append(callback)\n",
    )
    with RunContext(target_for(script, tmp_path)) as run:
        run.run()
    (callback,) = registry.items
    assert callback() == "still here"


def test_exception_still_restores_state(tmp_path: Path) -> None:
    """A failing script raises, and the process state is restored anyway."""
    script = write(tmp_path / "s.py", "import sys\nsys.argv.append('x')\n1 / 0\n")
    before = list(sys.argv)
    with (
        pytest.raises(ZeroDivisionError),
        RunContext(target_for(script, tmp_path)) as run,
    ):
        run.run()
    assert sys.argv == before


def test_project_package_runs_with_relative_imports(
    tmp_path: Path, registry: ModuleType
) -> None:
    """Projects run as packages, so relative imports work like `python -m`."""
    src = tmp_path / "proj" / "src"
    write(src / "pkg" / "__init__.py", "")
    write(src / "pkg" / "words.py", "WORD = 'relative ok'\n")
    entry = write(
        src / "pkg" / "__main__.py",
        "import runner_registry\n"
        "from .words import WORD\n"
        "if __name__ == '__main__':\n"
        "    runner_registry.items.append(WORD)\n",
    )
    with RunContext(target_for(entry, src)) as run:
        run.run()
    assert registry.items == ["relative ok"]
    assert "pkg" not in sys.modules and "pkg.words" not in sys.modules


def test_close_is_idempotent(tmp_path: Path) -> None:
    """Closing twice (for example, two end-of-run paths racing) is harmless."""
    run = RunContext(target_for(write(tmp_path / "s.py", ""), tmp_path))
    run.open()
    before_close = list(sys.path)
    run.close()
    after = list(sys.path)
    run.close()
    assert sys.path == after and len(after) == len(before_close) - 1


# ---------------------------------------------------------------------------
# RunLifetime: plain script or takeover
# ---------------------------------------------------------------------------


class FakeLoop:
    """Queues callbacks in order, like asyncio's ready queue."""

    def __init__(self) -> None:
        self.ready: list[Callable[[], object]] = []

    def call_soon(self, callback: Callable[..., object], *args: object) -> None:
        """Queue `callback(*args)`."""
        self.ready.append(lambda: callback(*args))

    call_soon_threadsafe = call_soon

    def run_ready(self) -> None:
        """Run everything queued so far, including callbacks queued meanwhile."""
        while self.ready:
            self.ready.pop(0)()


def make_lifetime(
    stack: ObservableStack,
) -> tuple[RunLifetime, FakeLoop, list[BaseException | None]]:
    """A lifetime wired to a fake loop that records how runs finish."""
    loop = FakeLoop()
    finished: list[BaseException | None] = []
    lifetime = RunLifetime(stack, loop.call_soon_threadsafe, finished.append)
    return lifetime, loop, finished


def test_plain_script_finishes_after_body_returns() -> None:
    """No push onto the stack: the run ends as soon as the body returns."""
    lifetime, loop, finished = make_lifetime(ObservableStack())
    lifetime.body_finished()
    assert finished == []  # checked on the loop, not on the script thread
    loop.run_ready()
    assert finished == [None] and not lifetime.took_over


def test_takeover_via_call_soon_stays_open_until_pop() -> None:
    """A push queued just before the body returns is seen; the pop ends the run."""
    stack = ObservableStack([("launcher", object())])
    lifetime, loop, finished = make_lifetime(stack)
    loop.call_soon(stack.append, ("takeover", object()))  # template's call_soon
    lifetime.body_finished()
    loop.run_ready()
    assert lifetime.took_over and finished == []
    stack.pop()
    assert finished == []  # case F: finishing waits until the pop has completed
    loop.run_ready()
    assert finished == [None]


def test_nested_takeover_ends_only_back_at_start_depth() -> None:
    """Two pushes need two pops before the run ends."""
    stack = ObservableStack()
    lifetime, loop, finished = make_lifetime(stack)
    stack.append("a")
    stack.append("b")
    lifetime.body_finished()
    loop.run_ready()
    stack.pop()
    loop.run_ready()
    assert finished == []
    stack.pop()
    loop.run_ready()
    assert finished == [None]


def test_finishes_once_and_reports_error() -> None:
    """Extra pops or checks never finish a run twice; errors are passed on."""
    stack = ObservableStack()
    lifetime, loop, finished = make_lifetime(stack)
    error = ValueError("boom")
    lifetime.body_finished(error)
    lifetime.body_finished(error)
    loop.run_ready()
    stack.append("x")
    stack.pop()
    loop.run_ready()
    assert finished == [error]


def test_observable_stack_wraps_existing_list() -> None:
    """Upgrading the window's plain list keeps its entries and order."""
    stack = ObservableStack(["a", "b"])
    assert list(stack) == ["a", "b"] and isinstance(stack, list)


def test_package_module_entry_point_keeps_relative_imports(
    tmp_path: Path, registry: ModuleType
) -> None:
    """src/pkg/app.py with `from .two import X` works, as it did before #75."""
    src = tmp_path / "proj" / "src"
    write(src / "pkg" / "__init__.py", "")
    write(src / "pkg" / "two.py", "X = 2\n")
    entry = write(
        src / "pkg" / "app.py",
        "import runner_registry\n"
        "from .two import X\n"
        "runner_registry.items.append((__name__, X))\n",
    )
    with RunContext(target_for(entry, src)) as run:
        run.run()
    assert registry.items == [("__main__", 2)]


# ---------------------------------------------------------------------------
# How a run ends (#64)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("printed", "error", "action"),
    [
        (False, False, "list"),
        (True, False, "stay"),
        (False, True, "list"),  # after the error dialog is dismissed
        (True, True, "stay"),  # the output explains the error
    ],
)
def test_end_action(printed: bool, error: bool, action: str) -> None:
    """Return to the list only when there's nothing left to read."""
    assert end_action(printed=printed, error=error) == action


def test_pop_from_another_thread_finishes_on_the_loop() -> None:
    """Case D: a done callback on the script thread doesn't finish off-loop."""
    import threading

    stack = ObservableStack()
    lifetime, loop, finished = make_lifetime(stack)
    stack.append("takeover")
    lifetime.body_finished()
    loop.run_ready()

    worker = threading.Thread(target=stack.pop)
    worker.start()
    worker.join()
    assert finished == []  # only queued
    loop.run_ready()
    assert finished == [None]


class FakeWindow:
    """Just enough of a window for the stack's floor."""

    title = "Launcher"
    content = "launcher content"


def test_extra_pop_at_the_floor_is_ignored() -> None:
    """Case E: a second Back can't pop below where the run started."""
    stack = ObservableStack([("outer", "outer content")])
    stack.window = FakeWindow()
    stack.floor = 1
    stack.append(("Launcher", "launcher content"))
    assert stack.pop() == ("Launcher", "launcher content")  # the real Back
    # The double tap: keeps the launcher showing, outer entry stays put
    assert stack.pop() == ("Launcher", "launcher content")
    assert list(stack) == [("outer", "outer content")]


def test_floor_without_window_raises() -> None:
    """Without a window to keep, an extra pop fails like an empty list."""
    stack = ObservableStack(["a"])
    stack.floor = 1
    with pytest.raises(IndexError):
        stack.pop()


# ---------------------------------------------------------------------------
# Entry points (#94)
# ---------------------------------------------------------------------------

TOOLS = """
import sys

import runner_registry

SETTINGS = {"colour": "blue"}


def ok():
    runner_registry.items.append(("ok", list(sys.argv)))


def fails():
    return 3


class Tool:
    @classmethod
    def run(cls):
        runner_registry.items.append(("Tool.run", list(sys.argv)))

    class Nested:
        @staticmethod
        def go():
            runner_registry.items.append(("Nested.go", None))
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A project with a src/ package of entry point targets."""
    write(tmp_path / "proj" / "src" / "eptools" / "__init__.py", "")
    write(tmp_path / "proj" / "src" / "eptools" / "cli.py", TOOLS)
    write(
        tmp_path / "proj" / "src" / "eptools" / "__main__.py",
        "import runner_registry\nrunner_registry.items.append(('main', __name__))\n",
    )
    return tmp_path / "proj"


def run_entry(project: Path, reference: str, kind: str = "cli", argv=()) -> dict:
    """Run one entry point of `project` the way the launcher does."""
    target = entry_target("tool", reference, kind, project, project / "src")  # type: ignore[arg-type]
    with RunContext(target, argv=argv) as context:
        return context.run()


@pytest.mark.parametrize(
    ("text", "module", "attrs"),
    [
        ("pkg", "pkg", ()),
        ("pkg.mod:func", "pkg.mod", ("func",)),
        ("pkg.mod:Class.method.attr", "pkg.mod", ("Class", "method", "attr")),
        (" pkg.mod : func ", "pkg.mod", ("func",)),
        ("pkg.mod:func [extra1, extra2]", "pkg.mod", ("func",)),
    ],
)
def test_parse_references(text: str, module: str, attrs: tuple) -> None:
    """References follow the PyPA syntax; extras are accepted and dropped."""
    assert Reference.parse(text) == Reference(module, attrs)


@pytest.mark.parametrize("text", ["", "1pkg", "pkg:", "pkg:a.", "pkg::a", "a b"])
def test_malformed_references(text: str) -> None:
    """Anything else is refused before a run starts."""
    with pytest.raises(ValueError):
        Reference.parse(text)


def test_entry_target_runs_from_the_project(project: Path) -> None:
    """argv[0] is the entry point's name; the project is the working directory."""
    target = entry_target("greet", "eptools.cli:ok", "cli", project, project / "src")
    assert (target.argv0, target.workdir, target.import_root) == (
        "greet",
        project,
        project / "src",
    )
    with pytest.raises(ValueError):
        entry_target("bad", "not a reference", "cli", project, project / "src")


def test_function_entry_point(project: Path, registry: ModuleType) -> None:
    """A function is called with argv set; state is restored after."""
    argv = list(sys.argv)
    run_entry(project, "eptools.cli:ok", argv=["--x", "1"])
    assert registry.items == [("ok", ["tool", "--x", "1"])]
    assert sys.argv == argv and "eptools" not in sys.modules


def test_methods_and_nested_attributes(project: Path, registry: ModuleType) -> None:
    """The runner follows attributes: classmethods and nested staticmethods."""
    run_entry(project, "eptools.cli:Tool.run")
    run_entry(project, "eptools.cli:Tool.Nested.go", kind="other")
    assert registry.items == [("Tool.run", ["tool"]), ("Nested.go", None)]


def test_module_only_reference_runs_as_main(
    project: Path, registry: ModuleType
) -> None:
    """A reference to a module alone runs it like python -m."""
    run_entry(project, "eptools", kind="other")
    assert registry.items == [("main", "__main__")]


def test_console_return_value_is_the_exit_status(
    project: Path, registry: ModuleType
) -> None:
    """Console scripts exit with what their function returns, like sys.exit(main())."""
    with pytest.raises(SystemExit) as raised:
        run_entry(project, "eptools.cli:fails")
    assert raised.value.code == 3
    # Other groups' return values are just results
    assert run_entry(project, "eptools.cli:fails", kind="other") == {"result": 3}


def test_non_callable_entry_point(project: Path, registry: ModuleType) -> None:
    """A value that can't be called says what it is."""
    with pytest.raises(NotRunnable, match="eptools.cli:SETTINGS is a dict"):
        run_entry(project, "eptools.cli:SETTINGS", kind="other")


def test_missing_attribute(project: Path, registry: ModuleType) -> None:
    """A reference to something that isn't there fails like Python would."""
    with pytest.raises(AttributeError):
        run_entry(project, "eptools.cli:missing")


def test_resolve_follows_attributes() -> None:
    """resolve() imports the module and walks the attribute path."""
    assert resolve(Reference("os.path", ("join",))) is os.path.join


class FakeApp:
    """Stands in for toga.App: creating one replaces the running app."""

    app: object = None

    def __init__(self) -> None:
        FakeApp.app = self
        self.main_window = None

    def main_loop(self) -> None:
        """Never called by the launcher."""


@pytest.fixture
def fake_toga(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """A stand-in "toga" module whose running app is a sentinel."""
    launcher_app = object()
    monkeypatch.setattr(FakeApp, "app", launcher_app)
    module = SimpleNamespace(App=FakeApp, launcher_app=launcher_app)
    monkeypatch.setitem(sys.modules, "toga", module)
    return module


def test_gui_entry_point_using_takeover_runs(
    project: Path, registry: ModuleType, fake_toga: SimpleNamespace
) -> None:
    """A GUI entry point that doesn't make its own app runs like any other."""
    run_entry(project, "eptools.cli:ok", kind="gui")
    assert registry.items == [("ok", ["tool"])]


def test_gui_entry_point_making_its_own_app_is_refused(
    project: Path, fake_toga: SimpleNamespace
) -> None:
    """Making a second app is refused, and the launcher's app is put back."""
    write(
        project / "src" / "eptools" / "gui.py",
        "import toga\n\n"
        "def main():\n    return toga.App()\n\n"
        "def made_but_kept():\n    toga.App()\n\n"
        "def crashes():\n    toga.App()\n    raise RuntimeError('no loop')\n",
    )
    for name in ("main", "made_but_kept", "crashes"):
        with pytest.raises(UnsupportedGui, match="can't host yet"):
            run_entry(project, f"eptools.gui:{name}", kind="gui")
        assert FakeApp.app is fake_toga.launcher_app


# ---------------------------------------------------------------------------
# exit() and sys.stdin
# ---------------------------------------------------------------------------


@pytest.fixture
def real_stdin(monkeypatch: pytest.MonkeyPatch) -> io.TextIOWrapper:
    """A real, closable sys.stdin, standing in for the app's."""
    read_end, write_end = os.pipe()
    os.close(write_end)
    stdin = io.TextIOWrapper(io.FileIO(read_end))
    monkeypatch.setattr(sys, "stdin", stdin)
    yield stdin
    stdin.close()


def test_exit_does_not_close_the_apps_stdin(
    tmp_path: Path, real_stdin: io.TextIOWrapper
) -> None:
    """site's exit() closes sys.stdin; only the run's guard is closed."""
    script = write(tmp_path / "bye.py", "import sys\nsys.stdin.close()\nexit()\n")
    with (
        pytest.raises(SystemExit) as done,
        RunContext(target_for(script, tmp_path)) as run,
    ):
        run.run()
    assert done.value.code is None
    assert sys.stdin is real_stdin and not real_stdin.closed


def test_stdin_guard_passes_reads_through(
    tmp_path: Path, real_stdin: io.TextIOWrapper
) -> None:
    """Until it's closed, the guard behaves like the stream it wraps."""
    with RunContext(target_for(write(tmp_path / "s.py", ""), tmp_path)):
        assert sys.stdin is not real_stdin
        assert sys.stdin.fileno() == real_stdin.fileno()
        assert sys.stdin.read() == ""
        sys.stdin.close()
        with pytest.raises(ValueError):
            sys.stdin.read()
    assert sys.stdin is real_stdin


def test_no_stdin_is_left_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Embedded Pythons may have no sys.stdin at all."""
    monkeypatch.setattr(sys, "stdin", None)
    with RunContext(target_for(write(tmp_path / "s.py", ""), tmp_path)):
        assert sys.stdin is None
    assert sys.stdin is None
