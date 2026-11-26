---
name: mypystub-app
description: Build or change a Python app made from MyPyStub's project template (or any Toga app meant to run inside MyPyStub), so that it runs both inside the MyPyStub launcher on iOS and Android and as a standalone Briefcase app. Use when working in such a project, or when moving a MyPyStub script into one. For a single-file script to paste into MyPyStub, use the mypystub-script skill instead.
---

# Building a MyPyStub app

MyPyStub runs Python on iPhone, iPad and Android. **New** on its List tab makes
a *project*: a Briefcase app that runs inside MyPyStub as it is, and also
builds on a computer for iOS, Android and the desktop. These are the rules for
writing the app so that all of these keep working.

## The shape of an app

- `src/<package>/app.py` is the app. Its `main()` is the entry point.
- `main()` **might** run on a worker thread: it does in MyPyStub and in the
  project's own bootstrap, but a standalone build could call it on the main
  thread. So it may block (`input()`, `getpass.getpass()`, long work), and it
  must **build or change the UI only on the main thread**: schedule that with
  `toga.App.app.loop.call_soon_threadsafe(build, app)`, which is right from
  either thread.
- A `main()` that returns without having shown a screen means the app has
  finished. An exception from it is shown with its traceback.
- Moving a MyPyStub script in: its `# /// script` block's `dependencies` and
  `requires-python` go in `[project]` in `pyproject.toml`, and its body goes
  in `main()` (see the project README, "From a script").

## Three kinds of app

Pick one; they can't be mixed in one screen.

1. **Console:** reads stdin and writes stdout and stderr (`print()`,
   `input()`, `getpass()`). MyPyStub shows them in its Script view, and so does
   the project's bootstrap. **There is no terminal:** no `curses`, no `rich`
   layouts, live displays or progress bars, no cursor movement or ANSI
   colour. Write plain lines; input arrives a line at a time.
2. **A Toga UI:**
   - **If `toga.App.app` exists** (MyPyStub, or the project's bootstrap),
     *take over* its main window: set `app.main_window.content` and `title`.
   - **If it doesn't**, the app is on its own: make a `toga.App` with a
     `startup` that builds the screen, and call its `main_loop()`.
   - **The takeover protocol:** if `main_window` has a `content_stack` (a
     list), push `(window.title, window.content)` onto it before taking over,
     show a **Back** button, and on Back pop and restore. Without a
     `content_stack` there's nothing to go back to: hide Back. The template's
     `app.py` shows how. It is plain Toga, so the app needs no MyPyStub API.
3. **Web-based ("Positron"):** the UI is HTML, CSS and JavaScript in a
   `toga.WebView` that takes over the window as in 2. Give the page with
   `WebView.set_content(root_url, html)`, or serve the files with a small
   server (`http.server` on `127.0.0.1`, port 0, on a daemon thread) and set
   the WebView's `url` to it: a WebView shows only `http://` and `https://`
   URLs, never `file://`.

## What the code may use

- **Standard Python, Toga, Rubicon (iOS) and Chaquopy's `java` (Android).**
  Never `import mypystub`: the app must run without the launcher.
- **Only the part of Toga that iOS, Android and the desktop all have.**
  Check each widget in Toga's backend docs before using it: `Table` and
  `Tree`, for instance, aren't on iOS (use `DetailedList`).
- **Anything more goes in a platform-guarded bridge:** one small module per
  feature, with the native code inside `if sys.platform == "ios":` (Rubicon,
  `toga_iOS.libs`; `ObjCClass` only for classes `toga_iOS.libs` doesn't
  provide) and `if sys.platform == "android":` (`from java import jclass`),
  and a plain fallback everywhere else, so it imports and does something
  sensible on every platform.
- **Dependencies:** pure-Python packages where feasible. Otherwise a package
  must have binary wheels for **both iOS and Android on PyPI**. Nothing that
  needs a compiler or a separate executable at install time.

## The platforms

- **iOS and Android:** no `subprocess`, `os.system`, `multiprocessing` or
  anything else that starts a process, and no separate executables. Each app
  is **sandboxed**: it sees its own folders, not the rest of the device.
  Threads work. Network access works, but ask for nothing the user hasn't
  allowed (see the permissions in `pyproject.toml`).
- **Android** runs Python through Chaquopy; Back is the system's Back gesture,
  which the bootstrap sends through `content_stack`.
- **Desktop (macOS, Windows, Linux):** everything above still applies, so that
  the same code runs on the phones. Platform features need a fallback here,
  not a crash.

## Files

**File access is sandboxed. Don't assume the app's own files are writable:**
inside MyPyStub the Examples are read-only, and on a phone the app's folder
can't be written. Write to `toga.App.app.paths.data` (kept), `paths.cache`
(may be cleared) or `paths.config`, creating the folder first
(`mkdir(parents=True, exist_ok=True)`). Read the app's own resources relative
to `__file__`.

## Files you must not edit

They're shared with MyPyStub, and updating the project replaces them:

- `src/<package>/bootstrap.py` and `src/<package>/__main__.py`
- `src/<package>/hooks.py`, `script_tab.py`, `run_status.py`, `logfile.py`
  and `android_back.py`
- `android/java/` and `generate_icons.py`
- this skill, `.claude/skills/mypystub-app/SKILL.md`

In `pyproject.toml`, change only what its TODO comments point to: the
description, the author, `requires-python`, `dependencies`, the icon, and the
iOS permissions the app actually uses.

## Conventions

- Type hints on all functions; docstrings on public modules, classes and
  functions; lines of at most 88 characters; `ruff` for lint and format.
- Log with `logging.getLogger(__name__)`; `print()` is the app's output.
- Tests with `pytest` in `tests/`.
- Keep `app.py` readable on a phone: about 300 lines. Past that, split it into
  modules in the same package.

## Checking your work

- `briefcase dev` runs it on the computer; `uv run pytest` runs the tests.
- To try it in MyPyStub, share the project folder to the phone (or copy it,
  and use **Paste** on the List tab), then tap it.
- Check it both ways: inside MyPyStub (Back shown, returns to the launcher)
  and standalone (Back hidden).
