"""Count down slowly; the run lasts until the script returns."""

import sys
import time


def countdown(start: int, delay: float) -> None:
    """Print a countdown, pausing between numbers."""
    for n in range(start, 0, -1):
        print(f"{n}...")
        time.sleep(delay)
    print("Done!")


if __name__ == "__main__":
    # Optional arguments: how many seconds, and the pause between them
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    delay = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    countdown(start, delay)
