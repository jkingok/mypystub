---
name: mypystub-script
description: Write a complete, single-file Python script (PEP 723 inline metadata) that runs as it is in MyPyStub on iPhone, iPad and Android, and with `uv run` on a computer. Use when someone asks for a MyPyStub script or prototype, or a small Python or Toga app they can paste onto a phone, in one go. For a multi-file Briefcase project, use the mypystub-app skill instead.
---

# Writing a MyPyStub script

MyPyStub runs Python scripts on iPhone, iPad and Android. Someone copies a
script, taps **Paste** on MyPyStub's List tab, and taps the new row to run it.
The same file also runs on a computer with `uv run name.py`. Write the whole
script in one go, so it can be copied and pasted without changes.

## What to hand over

- **One file**, given in full in a single `python` code block: no
  placeholders, nothing elided, nothing to fill in.
- Say in a sentence what it does and that it's pasted with **Paste**.
- **About 300 lines at most.** It's read on a phone.

## The file's shape

```python
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "toga",
# ]
# ///
"""Tip calculator: split a bill and add a tip.

Anything after the first line is more detail. The first line is the
subtitle MyPyStub shows under the script's name.
"""

import toga

# ... functions and classes ...


def main() -> None:
    """Run it."""
    ...


if __name__ == "__main__":
    main()
```

- **The `# /// script` block comes first** (PEP 723): `requires-python`, and
  `dependencies` listing every package the script imports that isn't in the
  standard library, Toga included, so `uv run` can install them on a computer.
  MyPyStub installs them on first run.
- **The module docstring's first line** is a short description.
- **Nothing runs on import**: all the work is in `main()`, called from the
  `if __name__ == "__main__":` block. MyPyStub runs the file as `__main__`.

## Three kinds of script

1. **Console:** `print()`, `input()` and `getpass.getpass()`. MyPyStub shows
   them in its Script view, but **there is no terminal:** no `curses`, no
   `rich` layouts, live displays or progress bars, no cursor movement or ANSI
   colour. Write plain lines; input arrives a line at a time. No Toga needed.
2. **A Toga UI.** In MyPyStub the script runs on a worker thread inside an app
   that already exists (`toga.App.app`); on a computer there's no app yet.
   Handle both, in plain Toga:

   ```python
   from typing import Any

   import toga


   def build(app: toga.App) -> None:
       """Make the screen. Runs on the app's main thread."""
       window = app.main_window
       assert isinstance(window, toga.MainWindow)
       # MyPyStub keeps a stack of screens; push its screen to go back to
       stack: list[Any] | None = getattr(window, "content_stack", None)
       if stack is not None:
           stack.append((window.title, window.content))

       def back(widget: toga.Widget) -> None:
           if stack:
               window.title, window.content = stack.pop()

       window.title = "Tip calculator"
       window.content = toga.Column(
           margin=8,
           children=[
               toga.Button(
                   "‹ Back",
                   on_press=back,
                   visibility="visible" if stack is not None else "hidden",
               ),
               toga.Label("Hello"),
           ],
       )


   class Standalone(toga.App):
       """The app, when the script runs on its own (`uv run` on a computer)."""

       def startup(self) -> None:
           self.main_window = toga.MainWindow()
           build(self)


   def main() -> None:
       app = toga.App.app
       if app is not None:
           # Inside MyPyStub: change the screen on the main thread
           app.loop.call_soon_threadsafe(build, app)
       else:
           Standalone("Tip calculator", "org.example.tipcalculator").main_loop()
   ```

   Every change to widgets from another thread goes through
   `app.loop.call_soon_threadsafe(...)`; event handlers already run on the
   main thread. Long work goes on a `threading.Thread`, never in a handler.
3. **Web-based ("Positron"):** the UI is HTML, CSS and JavaScript in a
   `toga.WebView`, which takes over the window as in 2. Give it the page with
   `WebView.set_content("http://localhost/", html)`, or serve files with
   `http.server` on `127.0.0.1` (port 0) on a daemon thread and set the
   WebView's `url`. A WebView shows only `http://` and `https://` URLs.

## Limits (iOS and Android)

- **Only the part of Toga that iOS, Android and the desktop all have.** No
  `Table` or `Tree` (use `DetailedList`); check a widget's iOS and Android
  support in Toga's docs before using it.
- **No other processes:** no `subprocess`, `os.system`, `multiprocessing` or
  separate executables. Threads are fine.
- **Sandboxed files:** don't assume the script's own folder is writable (an
  example's isn't). Write to `toga.App.app.paths.data` (kept),
  `paths.cache` (may be cleared) or `paths.config`, after
  `mkdir(parents=True, exist_ok=True)`. A console script with no `toga.App.app`
  writes to the current folder, which MyPyStub sets to a writable one.
- **Dependencies:** pure-Python packages where feasible. Otherwise a package
  must have binary wheels for **both iOS and Android on PyPI**. Nothing that
  needs a compiler.
- **Platform features** (iOS through Rubicon and `toga_iOS.libs`, Android
  through `from java import jclass`) go inside `if sys.platform == "ios":` or
  `== "android":`, with a plain fallback for everything else.
- **Never `import mypystub`.** The script must run on its own too.

## Before handing it over

- It runs with `uv run name.py` on a computer: the Toga window opens with
  Back hidden, or the console script finishes.
- Inside MyPyStub, Back returns to the launcher, and nothing changes widgets
  off the main thread.
- Type hints and docstrings on functions; lines of at most 88 characters.
