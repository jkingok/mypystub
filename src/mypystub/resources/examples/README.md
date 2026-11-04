# Examples

Small scripts and projects to learn from and copy. Tap a folder to open it, and `..` to go back. Tap a script to run it. Swipe left on a row for **Info**, which shows what it does and its source; swipe right for **Setup**, where you give a script command-line arguments and environment variables.

- `basics/`
    - `hello_world.py`: print a greeting.
    - `hello_you.py`: ask your name with `input()`.
    - `console.py`: Python's own console, for multi-line code such as `def` blocks. Errors appear in the *Errors and warnings* pane; `exit()` leaves the console.
    - `repl.py`: a tiny prompt built from `input`, `eval` and `print`. Variables persist between lines; `exit()` ends it.
    - `show_args.py`: list the arguments you set in **Setup**.
    - `show_env.py`: show the environment variables you name, or all of them.
    - `args_and_env.py`: greet each name given as an argument, using `$GREETING` if it's set.
    - `with_dependency.py`: needs a package from PyPI, which is installed the first time it runs.
    - `hello_project/`: a project folder with its own `pyproject.toml`, a package under `src/`, and a dependency. It appears in the list as one entry, "Hello Project".
- `projects/`
    - `two_tools/`: one project with several entry points, so it opens like a folder. `greet` and `shout` are console commands, `window` takes over the screen, and `hello` and `settings` belong to a plugin group (`settings` is a dictionary, so it can't run).
- `takeover/`
    - `back_button.py`: replace the launcher's screen with your own, then hand it back with a Back button.
    - `nested_takeover.py`: two screens deep; each Back goes up one, and the last one returns to the launcher.
- `threads/`
    - `countdown.py`: a script that keeps running until it finishes. Optional arguments: the count and the pause.
    - `main_thread.py`: change the screen from a script, which has to happen on the app's main thread.
- `errors/`
    - `main_thread_error.py`: an error raised on the main thread.
    - `test_error.py`: raises as soon as it is loaded, to show how errors are reported.
- `hardware/`
    - `where_am_i.py`: ask for location permission and print where you are. In the Simulator, set a location with Features → Location.
    - `take_photo.py`: take a photo and save it to your photo library. It needs a real device; the Simulator has no camera.
    - `router_check.py`: check whether your router answers (needs the local network permission).
    - `paste_diagnostics.py`: copy something first, then run this to see everything on the pasteboard and what **Paste** would do with it. It saves `paste_report.txt` and the raw data in `paste_dump/` to share.

Every script here also runs unchanged with plain `python`, or as a standalone Briefcase app.

When you write your own scripts, keep the file name different from any module you import (a script called `json.py` would hide the standard library's). Folder names can be anything.
