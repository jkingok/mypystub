"""How a run ended, as the Script view's status row says it (#293).

✅ for a normal end, ❌ for a failure, ⚠️ when it couldn't run at all, and ⏹
when it was stopped. An exception class with ``could_not_run = True`` means
the code couldn't be run at all. Standard library only.
"""

from __future__ import annotations

FINISHED = "✅ Finished"
DEPENDENCY_FAILED = "❌ Dependency install failed"
LOAD_FAILED = "❌ Couldn't load the script"
STOPPED = "⏹ Stopped"


def run_status(error: BaseException | None) -> str:
    """The status a run ends with: how it ended, marked good or bad.

    No error, or ``sys.exit()`` / ``sys.exit(0)``, is a normal end. Any other
    exit status, as at a terminal, is a failure; ``sys.exit("message")``
    exits with status 1 after printing the message, so the message is shown.
    """
    if error is None:
        return FINISHED
    if isinstance(error, SystemExit):
        code = error.code
        if code is None or code == 0:
            return FINISHED
        if isinstance(code, int):
            return f"❌ Exited with status {code}"
        return f"❌ Exited: {code}"
    if getattr(type(error), "could_not_run", False):
        return "⚠️ Couldn't run"
    return f"❌ Failed: {type(error).__name__}"


def exit_status(code: int) -> str:
    """The status for a subprocess that exited with `code` (Native mode).

    As at a terminal: 0 is a normal end; a negative code is the signal that
    ended it (Stop sends one, but that run is reported as STOPPED instead).
    """
    if code == 0:
        return FINISHED
    if code < 0:
        return f"❌ Ended by signal {-code}"
    return f"❌ Exited with status {code}"
