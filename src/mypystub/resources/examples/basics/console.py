"""The standard library's interactive console: multi-line Python, like `python`."""

import builtins
import code
import sys


class Console(code.InteractiveConsole):
    """code.InteractiveConsole, writing its messages with print().

    The console writes its banner and tracebacks to sys.stderr. print() is
    used instead, so they appear wherever print() does: the terminal, or the
    Script tab when run in MyPyStub.
    """

    def write(self, data: str) -> None:
        """Show console output such as tracebacks."""
        print(data, end="")


def show(value: object) -> None:
    """Print an expression's result, like the interactive prompt does."""
    if value is not None:
        builtins._ = value  # type: ignore[attr-defined]
        print(repr(value))


def main() -> None:
    """Run the console until exit(), then come back here."""
    # Expression results normally go through sys.displayhook to sys.stdout
    previous, sys.displayhook = sys.displayhook, show
    try:
        # local_exit: exit() ends the console, not the whole program
        Console(local_exit=True).interact(
            banner="Python console. Blocks such as def need a blank line to end. "
            "exit() leaves.",
            exitmsg="Bye!",
        )
    finally:
        sys.displayhook = previous


if __name__ == "__main__":
    main()
