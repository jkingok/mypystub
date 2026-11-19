# App Template

App Template description

- `src/app_template/app.py` is your app: its `main()` builds the screen.
- `src/app_template/bootstrap.py` starts it as an app of its own, like
  MyPyStub's Script tab: a window showing its output (`script_view.py`), where
  `input()` and `getpass()` are answered, a log in the app's Documents, a
  **Restart** button, and Android's Back (`android_back.py`). In MyPyStub the
  launcher does all that instead, so the bootstrap only calls `app.main()`.
- `android/java/` holds the two Java classes Android needs: the documents
  provider (Documents in the Files app) and Back.
- `assets/src_icon.png` is the icon; replace it with your own (a large square
  PNG).

MyPyStub has no editor for `pyproject.toml`: its TODO comments say where your
dependencies go. Change it in any text editor.

## Moving it to a computer

Copy the folder (Share it from MyPyStub), then, with uv and Briefcase installed,
make the icons once:

```bash
uv run generate_icons.py
```

```bash
briefcase dev
```

```bash
briefcase run iOS
```

```bash
briefcase run android
```

## From a script

A MyPyStub script moves here by moving its text:

1. Copy the script's code (its imports, `main()` and anything else) over
   `src/app_template/app.py`. Leave out the `# /// script` block.
2. Copy that block's keys into `[project]` in `pyproject.toml`: they have the
   same names, `requires-python` and `dependencies`. That is the only place
   dependencies go: MyPyStub reads them from there, and Briefcase adds them to
   the built app.
3. Put the script's first docstring line in `[project]`'s `description`.

`main()` runs the same way in both: on a thread of its own, with `print`,
`input()` and `getpass()` going to the Script view, and a takeover (setting the
window's content) working as it does in MyPyStub.
