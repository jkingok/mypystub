# MyPyStub

Is a *Python* engine for your iPhone or iPad.

You can run _basic_ Python scripts in an environment where it will allow you answer `input()` and `print()` as
appears in basic examples.

Or a more sophisticated UI using BeeWare's *Toga* can be used.

_There are some important steps to integrating your own Toga script within the limitations of iOS, so I recommend you start with my template._

The app is made up of the following views:

## List

A list of Python modules and scripts found in the *On My* (iPhone/iPad) section of *Files* under *MyPyStub*.

Select the item to run it.

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

Another way to modify the behaviour of the app is to replace the launcher completely by placing a `patch_app.py` into the same "MyPyStub" folder.

## Help

This help page! You are here.





