"""Logging goes to the log file, never a script's output, unless a script says so."""

from __future__ import annotations

import ast
import io
import logging
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

import mypystub
import togax_jkingok
from mypystub import logfile
from mypystub.runner import RunContext, RunTarget


@pytest.fixture
def restored() -> Iterator[None]:
    """Put stdout, stderr and logging back after the test."""
    saved = sys.stdout, sys.stderr, logfile._current, logging.lastResort
    levels = {name: logging.getLogger(name).level for name in logfile.APP_LOGGERS}
    handlers, root_level = list(logging.root.handlers), logging.root.level
    yield
    sys.stdout, sys.stderr, logfile._current, logging.lastResort = saved
    for name, level in levels.items():
        logging.getLogger(name).setLevel(level)
    logging.root.handlers[:] = handlers
    logging.root.setLevel(root_level)


def installed(tmp_path: Path) -> logfile.LogRedirector:
    """Install the log, with the root logger as bare as it is in the app.

    pytest puts its capture handlers on the root logger as each test starts;
    the app has none, so records fall through to the handler of last resort.
    (The `restored` fixture puts them back.)
    """
    logging.root.handlers[:] = []
    redirector = logfile.install(tmp_path / "app_runtime.log")
    redirector.terminal = None  # keep the test's own terminal quiet
    return redirector


def logged(redirector: logfile.LogRedirector) -> str:
    redirector.flush()
    return redirector.path.read_text()


def test_the_launchers_info_reaches_the_log_not_the_scripts_output(
    tmp_path: Path, restored: None
) -> None:
    redirector = installed(tmp_path)
    script_output = io.StringIO()
    sys.stdout = sys.stderr = script_output  # as while a script runs
    logging.getLogger("togax_jkingok.safe_area").info("SafeArea[Box] padding applied")
    logging.getLogger("mypystub.piplike").info("downloading x")
    assert "INFO togax_jkingok.safe_area: SafeArea[Box] padding applied" in logged(
        redirector
    )
    assert "INFO mypystub.piplike: downloading x" in logged(redirector)
    assert script_output.getvalue() == ""


def test_any_logger_with_no_handler_goes_to_the_log(
    tmp_path: Path, restored: None
) -> None:
    """Not routed by module: a script's or a library's logging lands there too."""
    redirector = installed(tmp_path)
    script_output = io.StringIO()
    sys.stderr = script_output
    logging.getLogger("some_library").warning("careful")
    logging.getLogger("some_library").info("chatter")  # below its WARNING level
    assert "WARNING some_library: careful" in logged(redirector)
    assert "chatter" not in logged(redirector)
    assert script_output.getvalue() == ""


def test_installing_twice_writes_each_line_once(tmp_path: Path, restored: None) -> None:
    installed(tmp_path / "first")
    redirector = installed(tmp_path)
    logging.getLogger("togax_jkingok.safe_area").info("once")
    assert logged(redirector).count("once") == 1
    assert "once" not in (tmp_path / "first" / "app_runtime.log").read_text()


def test_a_script_that_configures_logging_gets_it_until_it_ends(
    tmp_path: Path, restored: None
) -> None:
    redirector = installed(tmp_path)
    script = tmp_path / "script.py"
    script.write_text(
        "import logging, sys\n"
        "logging.basicConfig(stream=sys.stdout, format='%(message)s', level='INFO')\n"
        "logging.getLogger('mine').info('from the script')\n"
    )
    script_output = io.StringIO()
    sys.stdout = script_output
    with RunContext(
        RunTarget(path=script, import_root=tmp_path, workdir=tmp_path)
    ) as run:
        run.run()
    assert script_output.getvalue() == "from the script\n"  # its choice, honoured
    assert logging.root.handlers == []  # and gone when it ends
    logging.getLogger("mine").warning("after")
    assert "after" in logged(redirector) and "after" not in script_output.getvalue()


def prints_in(folder: Path, skip: Path | None = None) -> list[str]:
    found = []
    for path in sorted(folder.rglob("*.py")):
        if skip is not None and path.is_relative_to(skip):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                found.append(f"{path.relative_to(folder.parent)}:{node.lineno}")
    return found


def test_the_launcher_and_widgets_log_instead_of_printing() -> None:
    """print() goes to whatever stdout is, which is a script's output in a run."""
    app = Path(mypystub.__file__).parent
    assert prints_in(app, skip=app / "resources") == []
    assert prints_in(Path(togax_jkingok.__file__).parent) == []
