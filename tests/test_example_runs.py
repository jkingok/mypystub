"""Run the bundled examples for each run mode through the launcher's runner (#60).

These cover the examples that need no UI, device or network. Takeovers are run
on the dummy backend in tests/test_ui.py.
"""

import os
import sys
from pathlib import Path

import pytest

import mypystub
from mypystub import scan
from mypystub.runner import RunContext, target_for

EXAMPLES = Path(mypystub.__file__).parent / "resources" / "examples"


def run_example(relative: str, argv: list[str] = (), env: dict | None = None) -> None:
    """Run an example the way the launcher does."""
    path = EXAMPLES / relative
    with RunContext(target_for(path, path.parent), argv=argv, env=env) as run:
        run.run()


def test_plain_script(capsys: pytest.CaptureFixture[str]) -> None:
    """Plain script: runs top to bottom; the run ends when it returns."""
    run_example("basics/hello_world.py")
    assert capsys.readouterr().out == "Hello world!\n"


def test_long_running_script(capsys: pytest.CaptureFixture[str]) -> None:
    """Long-running script: the run lasts until its loop finishes."""
    run_example("threads/countdown.py", argv=["3", "0"])
    assert capsys.readouterr().out.splitlines() == ["3...", "2...", "1...", "Done!"]


def test_arguments_and_environment(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """argv and environment variables reach the script, then are restored."""
    monkeypatch.delenv("GREETING", raising=False)
    argv, environ = list(sys.argv), dict(os.environ)
    run_example("basics/args_and_env.py", argv=["Ada", "Grace"], env={"GREETING": "Hi"})
    assert capsys.readouterr().out.splitlines() == ["Hi, Ada!", "Hi, Grace!"]
    assert (list(sys.argv), dict(os.environ)) == (argv, environ)


def test_arguments_have_defaults(capsys: pytest.CaptureFixture[str]) -> None:
    """With no arguments or environment, the example still says something."""
    run_example("basics/args_and_env.py")
    assert capsys.readouterr().out.strip() == "Hello, world!"


def test_dependency_example_declares_its_dependency() -> None:
    """The dependency example's PEP 723 block is what the launcher installs from."""
    (entry,) = [
        e
        for e in scan.scan_all_prototypes(EXAMPLES / "basics")
        if e["title"] == "with_dependency"
    ]
    assert entry["dependencies"] == ["humanize"]


def test_show_args_lists_each_argument(capsys: pytest.CaptureFixture[str]) -> None:
    """show_args numbers each argument set with Setup, keeping their order."""
    run_example("basics/show_args.py", argv=["--name", "Ada Lovelace", ""])
    assert capsys.readouterr().out.splitlines() == [
        "1: --name",
        "2: Ada Lovelace",
        "3: ",
    ]


def test_show_args_without_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    """With no arguments, show_args says how to set some."""
    run_example("basics/show_args.py")
    assert capsys.readouterr().out.startswith("No arguments.")


def test_show_env_named_variables(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """show_env prints the variables named as arguments, set or not."""
    monkeypatch.delenv("MISSING_ONE", raising=False)
    run_example(
        "basics/show_env.py", argv=["GREETING", "MISSING_ONE"], env={"GREETING": "Hi"}
    )
    assert capsys.readouterr().out.splitlines() == [
        "GREETING=Hi",
        "MISSING_ONE is not set",
    ]


def test_show_env_lists_everything_sorted(capsys: pytest.CaptureFixture[str]) -> None:
    """With no arguments, show_env lists every variable, alphabetised."""
    run_example("basics/show_env.py", env={"AAA_FIRST": "1", "zzz_last": "2"})
    names = [line.split("=", 1)[0] for line in capsys.readouterr().out.splitlines()]
    assert "AAA_FIRST" in names and "zzz_last" in names
    assert names == sorted(names, key=str.casefold)


TWO_TOOLS = EXAMPLES / "projects" / "two_tools"


def run_two_tools(name: str, argv: list[str] = (), env: dict | None = None) -> dict:
    """Run one of Two Tools' entry points the way the launcher does."""
    from mypystub.runner import entry_target

    package = scan.scan_project(TWO_TOOLS)  # scan_project doesn't print
    (entry,) = [e for e in package["entries"] if e.name == name]
    target = entry_target(
        entry.name, entry.reference, entry.kind, TWO_TOOLS, TWO_TOOLS / "src"
    )
    with RunContext(target, argv=argv, env=env) as run:
        return run.run()


def test_two_tools_lists_every_kind_of_entry_point() -> None:
    """The project opens like a folder of its entry points."""
    (package,) = scan.scan_all_prototypes(EXAMPLES / "projects")
    assert package["kind"] == "package" and package["title"] == "Two Tools"
    assert [(e.name, e.label) for e in package["entries"]] == [
        ("greet", "Console"),
        ("hello", "two_tools.plugins"),
        ("settings", "two_tools.plugins"),
        ("shout", "Console"),
        ("window", "GUI"),
    ]


def test_two_tools_console_entry_points(capsys: pytest.CaptureFixture[str]) -> None:
    """greet reads --name and $GREETING; shout is a classmethod."""
    with pytest.raises(SystemExit) as done:
        run_two_tools("greet", argv=["--name", "Ada"], env={"GREETING": "Hi"})
    assert done.value.code == 0
    run_two_tools("shout", argv=["quiet", "please"])
    assert capsys.readouterr().out.splitlines() == ["Hi, Ada!", "QUIET PLEASE"]


def test_two_tools_plugin_entry_points(capsys: pytest.CaptureFixture[str]) -> None:
    """A callable plugin runs; a dictionary can't."""
    from mypystub.runner import NotRunnable

    run_two_tools("hello")
    assert capsys.readouterr().out.startswith("Hello from a plugin.")
    with pytest.raises(NotRunnable, match="is a dict"):
        run_two_tools("settings")


def test_repl_keeps_variables_and_ends_on_exit(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Variables persist between lines; errors are shown; exit() ends the run."""
    lines = iter(
        [
            "x = 6",
            "x * 7",
            "",
            "import math",
            "math.pi > 3",
            "1 / 0",
            "print('hi')",
            "exit()",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    with pytest.raises(SystemExit) as done:
        run_example("basics/repl.py")
    assert done.value.code is None  # a normal end, like at the terminal
    assert capsys.readouterr().out.splitlines() == [
        "Type Python. exit() ends the loop.",
        "42",
        "True",
        "ZeroDivisionError: division by zero",
        "hi",
    ]


def test_console_runs_blocks_like_a_terminal(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Multi-line blocks work; results go to stdout, banner and errors to stderr."""
    lines = iter(
        ["def f(n):", "    return n * 7", "", "f(6)", "1 / 0", "_ + 1", "exit()"]
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    run_example("basics/console.py")  # exit() ends the console, not the run
    out, err = capsys.readouterr()
    assert out.splitlines() == ["42", "43"]  # results, and _ is the last one
    assert "Python console." in err and "Bye!" in err
    assert "ZeroDivisionError: division by zero" in err


def test_console_prints_errors_even_when_an_app_hooks_them(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The launcher's sys.excepthook (an error dialog) isn't used by the console."""
    lines = iter(["1 / 0", "exit()"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    hooked: list[BaseException] = []

    def app_hook(typ: type, value: BaseException, tb: object) -> None:
        hooked.append(value)

    monkeypatch.setattr(sys, "excepthook", app_hook)
    run_example("basics/console.py")
    assert "ZeroDivisionError: division by zero" in capsys.readouterr().err
    assert hooked == [] and sys.excepthook is app_hook
