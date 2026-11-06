# What's New

## 2026.11.6.1 (2026-11-06)

### New

- A script can now depend on a wheel at a web address, for example `foo @ https://example.com/foo-1.0-py3-none-any.whl`, optionally with `#sha256=` to check the file.
- A script can now depend on a pure-Python project from a GitHub address or a source archive, for example `toga-console @ https://github.com/beeware/toga-console`. Anything that needs compiling is refused with a reason, as is any wheel that isn't pure Python.
- Setup has a new "Open Documents in Files" button, which opens your Documents folder in the Files app.

### Fixed

- Fixed a script not running after an example such as Blog Master had been run: the launcher lost its own settings. Errors that used to appear only in the Log now show in a dialog. Pasted scripts are offered the name they were copied with and always saved as .py, and a pasted name never ends in a repeated extension such as .py.py. Copied text named notes.txt is saved as notes.py, and a plain text file can't be imported.
- Fixed the Media Hub example failing on its first run: its default settings were missing.
- A dependency that points at a URL or a git repository is now refused with an explanation, instead of installing a different package of the same name from PyPI.

## 2026.11.4.2 (2026-11-04)

### New

- A **New Folder** button sits beside **Paste** above the list, on its left. It makes a folder in the folder you are browsing. Both buttons are greyed out where nothing can be added: at the top, in the examples, and inside a project or zipapp. Empty folders show 🪣 Empty.
- Adding or editing an argument, a variable, or a pasted file name now asks in a small alert over the current screen instead of taking over the whole screen.
- Swipe right on a script or project and choose **Make Quick Start** to have the app offer to run it each time it opens. You're always asked first, and you can change or clear the choice from the Setup tab's **Clear Quick Start**.
- Paste now previews what it will add — a script's source, a file's or zipapp's details, or an archive's contents — with **Cancel** and **Import** at the top, so you can see what you're importing before it lands. You're still asked for a file name only when one is needed.
- The About page now has a **Share source code** button that shares a zip of the app's own Python code, exactly as it runs on your device. It's a way to read or check the running source yourself, without having to trust the Source link above it.
- Examples now include `claude/` and `joshua/`, two folders of extra scripts and apps to explore.

### Fixed

- The Paste button no longer shows as "P...te" on some iPhones: the buttons above the list now share the width.
- The Setup menu fills the screen the first time you open it, instead of staying narrow and to the left.
- Following a security review, a `patch_app.py` file in your MyPyStub folder is no longer run automatically at launch. It now appears in the list and runs like any other script, so no file can take over the app before you tap it.
- **Paste** now works with a file copied in the Files app, which used to say there was nothing to paste. If you copy a folder, or don't allow pasting, it tells you what to do.

## 2026.11.3.2 (2026-11-03)

### New

- The Help tab has a What's New page, which opens the first time you start a new version.
- The About page has a Source link to the code for the version you're running, and web links there open in your browser.
