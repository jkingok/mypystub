# Examples

Sample prototypes and scratch scripts. These are not tests and are not collected by pytest. They are kept here to show how prototypes are structured and to exercise specific Toga and threading behaviour on device.

- `hello_world.py`, `hello_you.py`: minimal Toga examples.
- `main_thread.py`, `main_thread_error.py`: threading against the Toga main thread, with and without the error case.
- `test_error.py`: raises on import, to exercise error display in the launcher. Do not rename it to `test_*`.

Only use Toga widgets supported on iOS (see `CLAUDE.md`).
