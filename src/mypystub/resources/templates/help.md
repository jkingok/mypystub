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

## Script

This is the input and output of a running app until it takes over the UI itself.

## Logs

This is the Python log messages especially from the startup. You can see a lot of errors from in here, though you may need to click Reload first.
Clear can be used when the log gets too long.

## Settings

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

Each run gets its own `sys.argv`, environment and working directory (the script's folder, or the project folder), and they are restored afterwards. Your own modules are reloaded on the next run, so edits take effect without restarting the app.

## Hardware

Prototypes can use your **location**, **camera**, **photo library** (to save images) and **local network**. iOS asks for permission the first time a prototype uses each one, and you can change your answer later in the Settings app. The Examples' `hardware/` folder has a script for each.

## Help

This help page! You are here.

## Credits

Icons: [Uicons by Flaticon](https://www.flaticon.com/uicons).
