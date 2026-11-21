"""The app's log file: output teed to the terminal and to ``app_runtime.log``.

``sys.stdout`` and ``sys.stderr`` are replaced at start-up by a
:class:`LogRedirector`. Emptying the log while the app runs is a method of the
redirector itself (:meth:`LogRedirector.truncate`), so it works through the one
open file handle, without a restart, and whatever the user's settings are: the
Preserve Logs switch only decides whether the log is emptied at start-up and
whether the Clear Now button is enabled, never how truncation works (#197).

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import TextIO


class LogRedirector:
    """Duplicates written output to the terminal and to a persistent log file.

    Output can arrive from script threads while the log is being emptied, so
    both go through one lock.
    """

    def __init__(self, log_path: Path, terminal: TextIO | None = None) -> None:
        """Open `log_path` for appending, making its folder if needed."""
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_path.open(mode="a", buffering=1, encoding="utf-8")
        self.terminal = terminal if terminal is not None else sys.__stdout__
        self._lock = threading.Lock()

    def isatty(self) -> bool:
        """Never a terminal, so programs don't try fancy output."""
        return False

    @property
    def path(self) -> Path:
        """Where the log is."""
        return self.log_path

    def write(self, message: str) -> None:
        """Write a message to the terminal and the log file together."""
        with self._lock:
            if self.terminal:
                self.terminal.write(message)
            self.log_file.write(message)

    def flush(self) -> None:
        """Flush the terminal and the log file."""
        with self._lock:
            if self.terminal:
                self.terminal.flush()
            self.log_file.flush()

    def size(self) -> int:
        """How many bytes the log holds now."""
        with self._lock:
            self.log_file.flush()
        try:
            return self.log_path.stat().st_size
        except OSError:
            return 0

    def truncate(self) -> int:
        """Empty the log through the open file; return how many bytes it held.

        Later output goes on being logged into the same file. Nothing here
        reads a setting: Clear Now, the startup policy and any size cap all
        call this one method.
        """
        before = self.size()
        with self._lock:
            self.log_file.flush()
            self.log_file.seek(0)
            self.log_file.truncate(0)
        return before


_current: LogRedirector | None = None


# The app's own packages log at INFO; everything else keeps logging's default
# (WARNING). These are levels only: where records go is decided once, for
# every logger, by the handler of last resort (see install)
APP_LOGGERS = ("mypystub", "togax_jkingok")
LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"


class LogFileHandler(logging.Handler):
    """Writes log records to the log file (through `redirector`), never stdout.

    ``sys.stdout`` is a running script's output while it runs, so a handler
    on it (as logging's own default, on stderr) would show the launcher's
    diagnostics among the script's. This one holds the redirector itself.
    """

    def __init__(self, redirector: LogRedirector) -> None:
        """Write to `redirector`'s log file (and its terminal echo)."""
        super().__init__(logging.NOTSET)
        self.redirector = redirector
        self.setFormatter(logging.Formatter(LOG_FORMAT))

    def emit(self, record: logging.LogRecord) -> None:
        """Write one record as a line."""
        try:
            self.redirector.write(self.format(record) + "\n")
        except Exception:  # noqa: BLE001  (logging must never raise)
            self.handleError(record)


def install(log_path: Path) -> LogRedirector:
    """Make a redirector for `log_path` the app's stdout and stderr.

    Logging goes to the log file too, from every logger: the redirector
    becomes logging's handler of last resort (``logging.lastResort``), which
    handles any record that no configured handler takes. So nothing logged
    reaches stdout or stderr unless someone configures it to, as a script
    can (``logging.basicConfig()`` and the like); the runner puts logging
    back as it was when the script ends.
    """
    global _current
    _current = LogRedirector(log_path)
    sys.stdout = _current  # type: ignore[assignment]
    sys.stderr = _current  # type: ignore[assignment]
    logging.lastResort = LogFileHandler(_current)
    for name in APP_LOGGERS:
        logging.getLogger(name).setLevel(logging.INFO)
    return _current


def current() -> LogRedirector | None:
    """The redirector :func:`install` made, if any (None in tests and dev runs)."""
    return _current
