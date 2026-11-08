"""Pick up where you left off: a counter that saves itself as it goes.

iOS can end an app in the background without warning. This is the pattern for a
script that survives that. It writes the little it needs to remember to a file
*as it goes*, and looks for that file when it starts. If the file is there, the
last run was cut short, so it carries on from there; if not, it starts fresh. It
is not told that it was resumed, and nothing here is specific to MyPyStub: it
works the same as a standalone program.

Run it, stop it part-way (go back to the list, or close the app), and run it
again. Optional argument: how high to count (default 20).
"""

import json
import os
import sys
import time
from pathlib import Path

import toga

NAME = "resume_counter.json"


def state_file() -> Path:
    """Where this script keeps its state: the app's data folder, else the home folder."""
    app = toga.App.app
    folder = Path(app.paths.data) if app else Path.home() / ".resume_counter"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / NAME


def load(path: Path) -> dict | None:
    """The saved state, or None if there is none or it can't be read."""
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def save(path: Path, state: dict) -> None:
    """Save the state whole, so a stop part-way never leaves half a file."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(state))
    os.replace(temporary, path)


def main() -> None:
    """Count up to a target, saving after every step."""
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    path = state_file()
    state = load(path)
    if state and state.get("target") == target and state.get("count", 0) < target:
        print(f"Welcome back: carrying on from {state['count']}.")
    else:
        state = {"count": 0, "target": target}
        print(f"Starting at 0, counting to {target}.")
    while state["count"] < target:
        time.sleep(0.5)
        state["count"] += 1
        save(path, state)  # saved as it goes, not at the end
        print(state["count"])
    path.unlink(missing_ok=True)  # finished: next time starts fresh
    print("Done. Run it again to start over.")


if __name__ == "__main__":
    main()
