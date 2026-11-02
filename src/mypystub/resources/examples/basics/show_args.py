"""List the command-line arguments, one per line, numbered."""

import sys


def main() -> None:
    """Print each argument after the script's name, or say there are none."""
    arguments = sys.argv[1:]
    if not arguments:
        print("No arguments. Swipe right on this script and choose Setup to add some.")
        return
    for number, argument in enumerate(arguments, start=1):
        print(f"{number}: {argument}")


if __name__ == "__main__":
    main()
