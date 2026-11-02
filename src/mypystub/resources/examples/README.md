# Examples

Sample prototypes and scratch scripts, shown in the app's **Examples** category. They live in `src/mypystub/resources/examples/` so Briefcase bundles them; the repo-level `examples/` is a symlink to this folder. These are not tests and are not collected by pytest.

They are grouped into folders the same way you can organise your own scripts in the Files app: tap a folder to open it, and `..` to go back. Each script starts with a one-line docstring, which the list shows as its description.

- `basics/` (its `README.md` is what Info shows for the folder)
  - `hello_world.py`: print a greeting.
  - `hello_you.py`: read input with `input()`.
  - `console.py`: the standard library's `code` console, for multi-line Python such as `def` blocks. Results and errors are shown with `print()` so they reach the Script tab; `exit()` leaves the console.
  - `repl.py`: a tiny read-eval-print loop built from `input`, `eval` and `print`. Variables persist between lines; `exit()` ends the run.
  - `show_args.py`: list the command-line arguments set with **Setup** (swipe right).
  - `show_env.py`: show the environment variables named as arguments, or all of them.
  - `args_and_env.py`: greet each name in `sys.argv`, using `$GREETING` if it's set.
  - `with_dependency.py`: declare a PyPI dependency in a PEP 723 block; it's installed on the first run.
  - `hello_project/`: a project folder with a `pyproject.toml`, a package under `src/`, and a dependency (`humanize`, installed on first run). It appears in the list as one entry, "Hello Project".
- `projects/`
  - `two_tools/`: one project with several entry points, listed as a folder. `greet` and `shout` are console entry points (`shout` is a classmethod), `window` is a GUI entry point that takes over the screen, and `hello` and `settings` are in a plugin group (`settings` is a dictionary, so it can't run). It also installs standalone with `pip install -e .`.
- `takeover/`
  - `back_button.py`: replace the launcher's screen with your own, then hand it back with a Back button. It pushes the launcher onto `main_window.content_stack` and pops it on Back, which is how the launcher knows the run has ended.
  - `nested_takeover.py`: two screens deep; each Back pops one, and the run ends back at the launcher.
- `threads/`
  - `countdown.py`: a long-running script; the run lasts until it returns. Optional arguments: the count and the pause.
  - `main_thread.py`: run work on the Toga main thread from a background script.
- `errors/`
  - `main_thread_error.py`: an error raised on the Toga main thread.
  - `test_error.py`: raises on import, to exercise error display in the launcher. It is not a pytest test; pytest only collects `tests/`.
- `hardware/`
  - `where_am_i.py`: ask for location permission and print your position. In the Simulator, set one with Features → Location.
  - `take_photo.py`: take a photo and save it to your photo library (camera and photo library permissions; needs a real device, the Simulator has no camera).
  - `router_check.py`: check whether your router answers (local network permission).

Each script's folder is importable while it runs, so avoid **file** names that match real modules (such as `toga.py` or `json.py`). Folder names are free, though the tests still keep them distinct from the standard library.

Only use Toga widgets supported on iOS (see `CLAUDE.md`).
