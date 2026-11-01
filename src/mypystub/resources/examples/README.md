# Examples

Sample prototypes and scratch scripts, shown in the app's **Examples** category. They live in `src/mypystub/resources/examples/` so Briefcase bundles them; the repo-level `examples/` is a symlink to this folder. These are not tests and are not collected by pytest.

They are grouped into folders the same way you can organise your own scripts in the Files app: tap a folder to open it, and `..` to go back. Each script starts with a one-line docstring, which the list shows as its description.

- `basics/`
  - `hello_world.py`: print a greeting.
  - `hello_you.py`: read input with `input()`.
- `threads/`
  - `main_thread.py`: run work on the Toga main thread from a background script.
- `errors/`
  - `main_thread_error.py`: an error raised on the Toga main thread.
  - `test_error.py`: raises on import, to exercise error display in the launcher. It is not a pytest test; pytest only collects `tests/`.
- `hardware/`
  - `where_am_i.py`: ask for location permission and print your position. In the Simulator, set one with Features → Location.
  - `take_photo.py`: take a photo and save it to your photo library (camera and photo library permissions; needs a real device, the Simulator has no camera).
  - `router_check.py`: check whether your router answers (local network permission).
- `maintenance/`
  - `wipe_site_packages_from_cache.py`: removes user-installed packages from the app cache.

When adding a folder, avoid names of real modules (such as `threading` or `toga`): the launcher names a script's module after its folder.

Only use Toga widgets supported on iOS (see `CLAUDE.md`).
