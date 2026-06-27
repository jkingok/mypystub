"""
My first application for prototyping with iDevices and Python
"""

import os
from pathlib import Path
import sys
import traceback

import toga
from toga.style.pack import COLUMN, ROW

class LogRedirector:
    """Redirects Python prints and errors to a persistent file on the iPhone."""
    def __init__(self, log_path):
        self.log_file = open(log_path, "a", encoding="utf-8", buffering=1)
        self.terminal = sys.__stdout__

    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)

    def flush(self):
        self.terminal.flush()
        self.log_file.flush()

class MyPyStub(toga.App):
    def startup(self):
        main_box = toga.Box(direction=COLUMN)

        name_label = toga.Label(
            "Your name: ",
            margin=(0, 5),
        )
        self.name_input = toga.TextInput(flex=1)

        name_box = toga.Box(direction=ROW, margin=5)
        name_box.add(name_label)
        name_box.add(self.name_input)

        button = toga.Button(
            "Say Hello!",
            on_press=self.say_hello,
            margin=5,
        )

        main_box.add(name_box)
        main_box.add(button)

        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = main_box
        self.main_window.show()

    def greeting(self):
        if self.name_input.value:
            return f"Hello, {self.name_input.value}"
        else:
            return "Hello, stranger"

    async def say_hello(self, widget):
        await self.main_window.dialog(
            toga.InfoDialog(
            self.greeting(),
            "Hi there!",
        )
    )

def stub_main():
    from . import launcher
    return launcher.main()

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
        print(f"⚡ Hot-Patch Intercepted on Device Storage: {hot_patch_file}")
        try:
            # Inject the Documents directory to the top of Python's import lookup array
            sys.path.insert(0, str(user_documents_dir))
            
            # Dynamically import the patch file you edited on your phone
            import patch_app
            
            print("✔ Hot-patch workspace parsed and executed flawlessly.")
            return patch_app.main()
            
        except Exception as e:
            print(f"❌ Hot-patch execution runtime failure: {e}")
            print("→ Gracefully routing application boot back to compiled factory core...")

    # 2. Standard Briefcase Fallback Loop
    # If no manual overrides are present on the phone, execute the standard production path.
    return stub_main()

def main():
    # Initialize the app container and hand window lifecycle execution over to Toga
    return bootstrap_application()

