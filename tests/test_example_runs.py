"""Run the bundled examples for each run mode through the launcher's runner (#60).

These cover the examples that need no UI, device or network. Takeovers are run
on the dummy backend in tests/test_ui.py.
"""

import os
import sys
from pathlib import Path

import pytest

import mypystub
from mypystub import piplike
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
        for e in piplike.scan_all_prototypes(EXAMPLES / "basics")
        if e["title"] == "with_dependency"
    ]
    assert entry["dependencies"] == ["humanize"]
