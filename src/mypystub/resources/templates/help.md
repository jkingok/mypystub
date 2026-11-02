# MyPyStub

Is a *Python* engine for your iPhone or iPad.

You can run _basic_ Python scripts in an environment where it will allow you answer `input()` and `print()` as
appears in basic examples.

Or a more sophisticated UI using BeeWare's *Toga* can be used.

_There are some important steps to integrating your own Toga script within the limitations of iOS, so I recommend you start with my template._

Simple scripts _might_ work but long running ones can detect the Toga environment and understand that they are initially on a background thread.
They can return to the main thread via the `asyncio` features. To gracefully hold control back rather than exiting the background thread early,
hold it open with a `threading.Event`.

The app is made up of the following views:

## List

The list opens on two categories:

- **Examples**: sample prototypes built into the app.
- **Documents**: your own scripts and projects, from the *On My* (iPhone/iPad) section of *Files* under *MyPyStub*.

Each row previews what's inside. Tap a folder to open it, and `..` to go back up. Tap a script or project to run it.

Swipe a row for more:

- **Swipe left: Info.** A folder or category shows its README (`README.md`, `README.txt` or `README`) if it has one. A script shows its docstring, dependencies, inline metadata and highlighted source; long scripts fold after the first 300 lines. A project shows what its `pyproject.toml` declares: version, authors, dependencies, entry points, links, README, licence and changelog. Raw HTML in these files is shown as text, and web links open in your browser.
- **Swipe right: Setup** sets the command-line arguments and environment variables for a script or project. Arguments keep the order you give them; select one and use ⤒ ↑ ↓ ⤓ to move it to the top, up, down or to the bottom. In both lists, + adds, ✎ edits and ⌫ deletes. Environment variables are listed A–Z, since their order doesn't matter. Their names can use only letters, digits and `_`, and can't start with a digit (like `MY_SETTING`), so a shell could use them too. Changes are saved as you make them; *Done* goes back. A plain tap runs with these settings.

Rows with nothing to show or run say why.

Environment variables are inherited. Those set on the Setup tab's **Environment** page reach every run, and a script or project can override them, or add its own, with its own *Setup* (swipe right). A project with several entry points has its own Setup too, with variables but no arguments, which its entry points inherit and can override in turn. Inherited variables show where they come from, such as "from Setup"; editing one sets an override here, and deleting the override uses the inherited value again.

## Script

This is the input and output of a running app until it takes over the UI itself.

## Logs

This is the Python log messages especially from the startup. You can see a lot of errors from in here, though you may need to click Reload first.
Clear can be used when the log gets too long.

## Settings

The Setup tab has these sections:

- **Projects**: create a new project from the template (below).
- **Environment**: environment variables every script and project inherits (see *Swipe right: Setup* above).
- **Packages**: how many packages your prototypes have installed, and their size. *Check for updates* asks [PyPI](https://pypi.org) for newer versions (through its [JSON API](https://docs.pypi.org/api/json/)), and *Update all* installs them. *Wipe user packages…* deletes them all; prototypes reinstall what they need on their next run, which needs the network.
- **Health**: *Check app health* compares the app's Python with [python.org's releases](https://www.python.org/downloads/) (through its [downloads API](https://www.python.org/api/v2/downloads/release/?is_published=true)): the latest dot release for this version, and the next version if it's out or in pre-release. It also compares the packages built into the app with PyPI. These can only be updated by a new build of the app.
- **App**: back up your files, or exit back to the launcher you came from.

Nothing is checked online until you tap a button.

Here is the tool which generates a new "Project" or module for you to edit. If I've done it right then this is _also_
a good enough example that can be built standalone using *Briefcase* into an app standalone via a Mac.

Notice that the template contains a way of building a navigation stack and allowing the user to return back to the launcher.
There is no "real" exit on iOS, except for manually throwing it away from the switcher.

This launcher will introspect the `pyproject.toml` to look for a name, description, icon and its dependencies. It will attempt to download pure-Python wheels from [PyPI](https://pypi.org) for any dependencies. _It cannot download iOS-specific wheels yet for packages that have binary extensions._

A single-file script can do the same in its [inline script metadata](https://packaging.python.org/en/latest/specifications/inline-script-metadata/) block. Its first docstring line is used as the description if it doesn't set one:

```python
# /// script
# dependencies = ["humanize"]
#
# [tool.stub_launcher]
# display_name = "Weather Now"
# description = "Current local weather."
# icon = "icons/globe.png"
# ///
```

Another way to modify the behaviour of the app is to replace the launcher completely by placing a `patch_app.py` into the same "MyPyStub" folder.

## How your script is run

Scripts run the way `python script.py` runs them: as `__main__`, with `sys.argv[0]` set to the script and the script's folder importable. A project entry point inside a package runs the way `python -m` would, so relative imports work: `src/<package>/__main__.py` like `python -m <package>`, and `src/<package>/app.py` like `python -m <package>.app`. Put the code that starts your script under `if __name__ == "__main__":`. The launcher no longer calls a `main()` function for you.

A run ends when your script returns. If your script takes over the screen, it must push the launcher onto `main_window.content_stack` and pop it again when the user goes back (the project template does this). The run then ends when it is popped. A takeover that replaces the window content without using the stack can't be detected.

Ways a script can run, each with an example in the Examples category:

- **Plain script**: `print` and `input` use the Script tab. The run ends when the script returns (`basics/hello_world.py`, `basics/hello_you.py`).
- **Long-running script**: keeps working, for example in a loop or waiting on a `threading.Event`; the run lasts until it returns (`threads/countdown.py`).
- **Main-thread work**: Toga widgets must be changed on the app's main thread, so schedule that work with `toga.App.app.loop.call_soon_threadsafe(...)` (`threads/main_thread.py`).
- **Arguments and environment variables**: read `sys.argv` and `os.environ` as usual; set them by swiping right and choosing *Setup* (`basics/args_and_env.py`, `basics/show_args.py`, `basics/show_env.py`).
- **Dependencies**: list them in a PEP 723 block, and they're installed before the first run (`basics/with_dependency.py`).
- **Project folder**: a folder with a `pyproject.toml` and its code under `src/` (`basics/hello_project/`).
- **Entry points**: a project's `[project.scripts]` (console), `[project.gui-scripts]` (GUI) and any other `[project.entry-points.<group>]`. A project with one entry point runs it when tapped. With several, it opens like a folder, one row per entry point. `[tool.stub_launcher] entry_point` overrides them all. A reference such as `pkg.cli:Tool.run` is followed attribute by attribute and called, with `sys.argv[0]` set to the entry point's name; one that names only a module runs it like `python -m`. A console entry point's return value is its exit status. GUI entry points work when they take over the window with `main_window.content_stack`; one that starts its own `toga.App` can't be hosted yet (`projects/two_tools/`).
- **Taking over the screen**: push onto `main_window.content_stack` and pop on Back; nested screens work too, and the run ends back at the launcher (`takeover/back_button.py`, `takeover/nested_takeover.py`).

Each run gets its own `sys.argv`, environment and working directory (the script's folder, or the project folder), and they are restored afterwards. Your own modules are reloaded on the next run, so edits take effect without restarting the app.

## Packages with compiled parts

The launcher installs your prototypes' dependencies from [PyPI](https://pypi.org) as pure-Python wheels. Packages with compiled (binary) parts need a wheel built specifically for iOS, which most projects don't publish yet. BeeWare tracks which packages have one in its [mobile wheels](https://beeware.org/mobile-wheels/) project. Projects build them with [cibuildwheel](https://cibuildwheel.pypa.io/), which supports iOS. Binary wheels can't be added to the app after it's built, so the useful ones are bundled with it.

Where a pure-Python replacement exists, the launcher can use it instead. These **aliases** are listed on the About page:

- **substitute**: install another package in its place. Built in: `pyyaml` → `pyyaml-pure`, which provides the same `yaml` module. By default it's only used when the original has no compatible wheel, and the version pin is ignored, because the two projects number their versions differently.
- **bundled**: already provided by the app. Built in: `toga` → the bundled `toga-core`.

You can add your own in `launcher.toml`, or for one script or project in `[tool.stub_launcher.aliases]`:

```toml
[tool.stub_launcher.aliases]
somepackage = { kind = "substitute", target = "somepackage-pure", when = "always" }
```

`when` is `"no_wheel"` (the default) or `"always"`; `specifier` is `"drop"` (the default) or `"keep"`.

## Hardware

Prototypes can use your **location**, **camera**, **photo library** (to save images) and **local network**. iOS asks for permission the first time a prototype uses each one, and you can change your answer later in the Settings app. The Examples' `hardware/` folder has a script for each.

**Changed your mind about a permission?** iOS only asks once. To change your answer, tap *Open Settings* in the Setup tab (its Permissions section shows what's allowed), or go to the Settings app → MyPyStub. A permission only appears there after a prototype has asked for it. The hardware examples offer to open Settings when a permission was declined.

## Help

This help page! You are here.

## Credits

Icons: [Uicons by Flaticon](https://www.flaticon.com/uicons).
