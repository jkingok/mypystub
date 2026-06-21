"""
My first application for prototyping with iDevices and Python
"""

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
        # 1. Establish the writeable iOS Documents playground path
        user_documents_dir = self.paths.data # os.path.expanduser("~/Documents")
    
        # Ensure the directory exists (it always should in an iOS sandbox)
        user_documents_dir.mkdir(parents=True, exist_ok=True)
    
        # 2. Immediately intercept ALL stdout, stderr, and tracebacks
        log_path = Path(user_documents_dir / "app_runtime.log")
        print(f"Data directory: {user_documents_dir}, log path: {log_path}")
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

        # 3. Look for replacement app to start instead
        hot_patch_file = user_documents_dir / "patch_app.py"
        self.app_instance = None
        
        if hot_patch_file.exists():
            print(f"[BOOT] Hot-Patch file detected at: {hot_patch_file}")
            try:
                # Inject Documents folder to the top of the import path lookup
                sys.path.insert(0, str(user_documents_dir))
                print(sys.path)

                import patch_app
                print("[BOOT] Hot-patch parsed and compiled cleanly.")
            
                # Wrap the instantiated app function so we can pass a success status
                self.app_instance = patch_app.main()
                boot_status = "Hot-Patch Active"
            
            except Exception as e:
                # Captures syntax errors, indentation issues, or missing names
                error_details = traceback.format_exc()
                print(f"[CRITICAL ERROR] Hot-patch failed execution:\n{error_details}")
                boot_status = "Hot-Patch Failed"
        else:
            print("[BOOT] No hot-patch found. Executing master compiled core.")
        
        if self.app_instance:
            # Let the app build its main windows and views first
            self.app_instance.startup()
            
            # Display the execution alert overlay right on your screen
            if boot_status == "Hot-Patch Active":
                app_instance.main_window.info_dialog(
                    "⚡ Engine Tweak Loaded",
                    "Running live modifications from patch_app.py successfully."
                )
            elif boot_status == "Hot-Patch Failed":
                app_instance.main_window.error_dialog(
                    "❌ Patch Crash Intercepted",
                    f"Your phone edit crashed during execution. Defaulting to factory code.\n\nCheck app_runtime.log for the traceback."
                )
        else:
            # We skip the alert for the pure factory bundle to avoid annoying popups during production loops
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

def main():
    return MyPyStub()
