"""Console entry points: greet and shout."""

import argparse
import os
import sys


def greet() -> int:
    """Greet --name (default: world), using $GREETING if it's set."""
    parser = argparse.ArgumentParser(prog="greet", description=greet.__doc__)
    parser.add_argument("--name", default="world")
    args = parser.parse_args()
    print(f"{os.environ.get('GREETING', 'Hello')}, {args.name}!")
    return 0


class Shout:
    """Say things loudly."""

    @classmethod
    def run(cls) -> None:
        """Print the command-line arguments in capitals."""
        words = " ".join(sys.argv[1:])
        print(words.upper() if words else "NOTHING TO SHOUT ABOUT")
