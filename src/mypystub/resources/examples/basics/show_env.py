"""Show environment variables: the ones named as arguments, or all of them."""

import os
import sys


def main() -> None:
    """Print NAME=value for each variable asked for, or every variable, sorted."""
    names = sys.argv[1:] or sorted(os.environ, key=str.casefold)
    for name in names:
        value = os.environ.get(name)
        print(f"{name}={value}" if value is not None else f"{name} is not set")


if __name__ == "__main__":
    main()
