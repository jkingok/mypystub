"""The log file redirector, and emptying it while the app runs (#197, #198)."""

import io
import sys
import threading
from pathlib import Path

import pytest

from mypystub import logfile


@pytest.fixture
def redirector(tmp_path: Path) -> logfile.LogRedirector:
    """A redirector writing to a temp log, with its terminal captured."""
    return logfile.LogRedirector(tmp_path / "logs" / "app.log", terminal=io.StringIO())


def test_output_goes_to_the_terminal_and_the_file(
    redirector: logfile.LogRedirector,
) -> None:
    """Both get every message, and the folder is made."""
    redirector.write("hello\n")
    redirector.flush()
    assert redirector.log_path.read_text() == "hello\n"
    assert redirector.terminal.getvalue() == "hello\n"  # type: ignore[union-attr]
    assert redirector.isatty() is False and redirector.path == redirector.log_path


def test_a_new_redirector_appends_to_what_is_there(tmp_path: Path) -> None:
    """Opening the log again does not empty it: that is a separate decision."""
    path = tmp_path / "app.log"
    first = logfile.LogRedirector(path, terminal=io.StringIO())
    first.write("one\n")
    first.flush()
    second = logfile.LogRedirector(path, terminal=io.StringIO())
    second.write("two\n")
    second.flush()
    assert path.read_text() == "one\ntwo\n"


def test_truncate_empties_the_file_and_reports_the_size(
    redirector: logfile.LogRedirector,
) -> None:
    """The bytes held come back, and the file is empty."""
    redirector.write("a" * 100 + "\n")
    assert redirector.size() == 101
    assert redirector.truncate() == 101
    assert redirector.log_path.read_text() == "" and redirector.size() == 0


def test_logging_goes_on_into_the_same_file_after_truncating(
    redirector: logfile.LogRedirector,
) -> None:
    """No restart: later output lands at the start of the emptied file."""
    redirector.write("before\n")
    redirector.truncate()
    redirector.write("after\n")
    redirector.flush()
    assert redirector.log_path.read_text() == "after\n"
    redirector.truncate()
    redirector.truncate()  # emptying an empty log is harmless
    assert redirector.size() == 0


def test_truncating_while_other_threads_write_loses_nothing_it_should_keep(
    redirector: logfile.LogRedirector,
) -> None:
    """Writers and truncation share a lock: every line is whole, none is torn."""
    stop = threading.Event()

    def writer(name: str) -> None:
        number = 0
        while not stop.is_set():
            number += 1
            redirector.write(f"{name} {number}\n")

    threads = [threading.Thread(target=writer, args=(f"t{i}",)) for i in range(3)]
    for thread in threads:
        thread.start()
    for _ in range(50):
        redirector.truncate()
    stop.set()
    for thread in threads:
        thread.join()
    redirector.flush()
    for line in redirector.log_path.read_text().splitlines():
        name, number = line.split(" ")
        assert name in {"t0", "t1", "t2"} and number.isdigit()


def test_install_replaces_stdout_and_stderr_and_can_be_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The app's one redirector is reachable by the rest of the app."""
    monkeypatch.setattr(sys, "stdout", sys.stdout)
    monkeypatch.setattr(sys, "stderr", sys.stderr)
    monkeypatch.setattr(logfile, "_current", None)
    assert logfile.current() is None
    installed = logfile.install(tmp_path / "app.log")
    assert logfile.current() is installed
    assert sys.stdout is installed and sys.stderr is installed
