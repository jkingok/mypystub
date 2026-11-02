"""The standard library's interactive console: multi-line Python, like `python`."""

import code


def main() -> None:
    """Run the console until exit(), then come back here.

    Results go to standard output, and the banner and tracebacks to standard
    error, as at a terminal; MyPyStub shows standard error in its own pane.
    """
    # local_exit: exit() ends the console, not the whole program
    code.interact(
        banner="Python console. Blocks such as def need a blank line to end. "
        "exit() leaves.",
        exitmsg="Bye!",
        local_exit=True,
    )


if __name__ == "__main__":
    main()
