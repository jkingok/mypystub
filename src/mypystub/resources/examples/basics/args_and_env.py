"""Greet everyone named on the command line, using $GREETING if it's set."""

import os
import sys


def main() -> None:
    """Print a greeting for each argument, or for the world."""
    greeting = os.environ.get("GREETING", "Hello")
    names = sys.argv[1:] or ["world"]
    for name in names:
        print(f"{greeting}, {name}!")


if __name__ == "__main__":
    main()
