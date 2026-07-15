"""
My first application for prototyping with iDevices and Python
"""

import os
from pathlib import Path
import sys
import traceback

import toga

class LogRedirector:
    """Redirects Python prints and errors to a persistent file on the iPhone."""
    def __init__(self, log_path):
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        self.log_file = open(log_path, "a", encoding="utf-8", buffering=1)
        self.terminal = sys.__stdout__

    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)

    def flush(self):
        self.terminal.flush()
        self.log_file.flush()

from . import ui

class MyApp(toga.App):
    def startup_into(app, fresh=False):
        """Construct and show the Toga application.

        Usually, you would add your application to a main content box.
        We then create a main window (with a name matching the app), and
        show the main window.
        """
        try:
            # Cannot query main window before it is created!
            if fresh: # not app.main_window:
                app.main_window = toga.MainWindow(title=app.formal_name)

            app.proto = ui.Prototype(host_app=app, on_done=lambda _: MyApp.unstack_from(app))

            # Update window context and inject the prototype layout
            t = getattr(app.proto, "title", app.formal_name)
            mw = app.main_window
            if mw.content:
                if not hasattr(mw, "content_stack"):
                    mw.content_stack = []
                mw.content_stack.append((mw.title, mw.content))
            mw.title = t
            mw.content = app.proto.get_content()
        except Exception as e:
            print(f"Exception occurred creating UI: {str(e)}")
        finally:
            if not app.main_window.visible:
                mw.show()

    def unstack_from(app):
        if hasattr(app.main_window, "content_stack") and len(app.main_window.content_stack) > 0:
            t, c = app.main_window.content_stack.pop()
            app.main_window.title = t
            app.main_window.content = c

    def startup(self):
        return MyApp.startup_into(self, True)

def bootstrap_application():
    """
    Checks the iOS device user sandbox folder dynamically on boot. 
    If an updated 'patch_app.py' script exists in the app's Documents 
    directory, it hooks it into the runtime engine instead of the 
    factory-compiled bundle.
    """
    # 1. Target the iOS App's local writable Documents container
    # On an iPhone, this maps straight to the app's folder inside the Files App.
    user_documents_dir = Path("~/Documents").expanduser() # same as toga.App.paths.data
    
    # Ensure the directory exists (it always should in an iOS sandbox)
    user_documents_dir.mkdir(parents=True, exist_ok=True)
    
    # 2. Immediately intercept ALL stdout, stderr, and tracebacks
    log_path = user_documents_dir / "app_runtime.log"

    redirector = LogRedirector(log_path)
    sys.stdout = redirector
    sys.stderr = redirector
    
    # Define a hidden or marker file
    readme = user_documents_dir / "README"
    
    if not readme.exists():
        try:
            readme.write_text("Use this folder for logging and customising this app.")
        except Exception as e:
            print(f"Failed to write placeholder: {e}")
    
    hot_patch_file = user_documents_dir / "patch_app.py"
    
    if hot_patch_file.exists():
        print(f"??? Hot-Patch Intercepted on Device Storage: {hot_patch_file}")
        try:
            # Inject the Documents directory to the top of Python's import lookup array
            sys.path.insert(0, str(user_documents_dir))
            
            # Dynamically import the patch file you edited on your phone
            import patch_app
            
            print("??? Hot-patch workspace parsed and executed flawlessly.")
            return patch_app.main()
            
        except Exception as e:
            print(f"??? Hot-patch execution runtime failure: {e}")
            print("??? Gracefully routing application boot back to compiled factory core...")

    # 2. Standard Briefcase Fallback Loop
    # If no manual overrides are present on the phone, execute the standard production path.
    return MyApp()

def main():
    if not (a := toga.App.app):
        return bootstrap_application()
    elif a.loop:
        a.loop.call_soon(lambda a=a: MyApp.startup_into(a))
    else:
        MyApp.startup_into(a)
    return None
