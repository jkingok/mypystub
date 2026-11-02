"""The standard library's interactive console: multi-line Python, like `python`."""

import code
import sys


def main() -> None:
    """Run the console until exit(), then come back here.

    Results go to standard output, and the banner and tracebacks to standard
    error, as at a terminal; MyPyStub shows standard error in its own pane.
    """
    # The console hands errors to sys.excepthook instead of printing them when
    # an app has replaced it (MyPyStub shows them in a dialog), so use
    # Python's own hook while the console runs
    previous, sys.excepthook = sys.excepthook, sys.__excepthook__
    try:
        # local_exit: exit() ends the console, not the whole program
        code.interact(
            banner="Python console. Blocks such as def need a blank line to end. "
            "exit() leaves.",
            exitmsg="Bye!",
            local_exit=True,
        )
    finally:
        sys.excepthook = previous


if __name__ == "__main__":
    main()
