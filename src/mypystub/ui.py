import asyncio
from markdown import markdown as md
from pathlib import Path
import shutil
import toga
from toga.style import Pack

from . import hooks as h
from . import piplike as pip
from . import settings as s

class LabelledProgress(toga.Box):
    def __init__(self, **kwargs):
        self.bar = toga.ProgressBar(flex=1)
        self.text = toga.Label("")
        super().__init__(
            direction="row",
            children=[
                self.bar,
                self.text
            ],
            **kwargs
        )

    def start(self, limit:int=0):
        self.bar.max = limit if limit > 0 else None
        self.bar.start()
        self.update(0)

    def update(self, value:int):
        if self.bar.max:
            if self.bar.max == 100:
                self.text.text = f"{value}%"
            else:
                self.text.text = f"{value}/{self.bar.max}"
        else:
            self.text.text = "" 
        self.bar.value = value
  
    def stop(self):
        if self.bar.max:
            self.update(self.bar.max)
        self.bar.stop() 

class LabelledActivity(toga.Box):
    def __init__(self, **kwargs):
        self.activity = toga.ActivityIndicator()
        self.text = toga.Label("", flex=1)
        super().__init__(
            direction="row",
            children=[
                self.activity,
                self.text
            ],
            **kwargs
        )

    def update(self, value:str="", on:bool=True):
        self.activity.start() if on else self.activity.stop()
        self.text.text=value 

class Prototype:
    def __init__(self, host_app, on_done):
        self.app = host_app
        self.on_done_callback = on_done  # This is your ticket back to safety
        self.title = "Launcher" # host_app.formal_name
        self.app.settings = s.Settings(host_app.paths)
        self.data_path = self.app.paths.data
        self.this_path = Path(__file__).resolve().parent
        self.icon_path = self.this_path / "resources" / "icons"
        self.template_path = self.this_path / "resources" / "templates"
        self.prototype_dir = self.data_path
        self.bootstrapped = pip.strict_manifest_preflight()
        self.input_prompt = toga.Label(
            "Input"
        )
        self.input_text = toga.TextInput(
            style=Pack(flex=1),
            on_gain_focus=lambda m: self.pad_keyboard(True),
            on_lose_focus=lambda m: self.pad_keyboard(False)
        )
        self.input_box = toga.Column(
                    children=[
                         self.input_prompt,
                         self.input_text
                    ],
                    text_align="center"
                )
        self.print_text = toga.MultilineTextInput(readonly=True) 
        self.script_runner = h.ScriptRunner(host_app, self.input_prompt, self.input_text, self.print_text, self.toggle_input)
        self.script_activity = LabelledActivity()
    
    async def todo(self, name):
        await self.app.main_window.dialog(toga.InfoDialog("TODO", name))
        
    async def info(self, text):
        await self.app.main_window.dialog(toga.InfoDialog("Info", text))

    def close_keyboard(self, widget):
        """Triggered when the user presses 'Return' or 'Done' on the iPad keyboard."""
        # Dismiss the keyboard by resigning First Responder status
        try:
            # Check if we are running on iOS/iPadOS via the native implementation handle
            if hasattr(widget, '_impl') and hasattr(widget._impl, 'native'):
                native_textfield = widget._impl.native
            
                # Fire the native UIKit selector to lower the keyboard
                native_textfield.resignFirstResponder()
                print("[UIKit] Keyboard dismissed via resignFirstResponder.")
        except Exception as e:
            # Graceful fallback for macOS/Windows desktop development runners
            print(f"[Platform Fallback] Could not reach native interface: {e}")
    
    def reload_logs(self, widget=None):
        logs = (self.data_path / "app_runtime.log").read_text()
        if widget:
            widget.app.widgets["log_text"].value = logs
        return logs 
    
    def reload_menu(self, widget=None):
        # 1. Gather all of our TOML configuration profiles
        self.prototypes_data = pip.scan_all_prototypes(self.prototype_dir)
        
        # 2. Format the records specifically for Toga's DetailedList expectations
        list_items = []
        for proto in self.prototypes_data:
            # Safely build a toga.Image if an icon path was specified and exists
            row_icon = None
            if proto["icon_path"] and proto["icon_path"].exists():
                row_icon = toga.Image(proto["icon_path"])
                
            list_items.append({
                "title": proto["title"],
                "subtitle": proto["subtitle"],
                "icon": row_icon,
                # Toga ignores these custom keys for rendering, but holds onto them for callbacks!
                "entry_point": proto["entry_point"],
                "folder_root": proto["folder_root"],
                "dependencies": proto["dependencies"]
            })
        
        if widget:
            widget.data = list_items
        return list_items

    def new_project(self, widget=None):
        def snake(s):
            return '_'.join(s.lower().split())  

        project_name = self.app.widgets["new_project_name"].value
        template_zip = self.template_path / "my_template.zip"
        target = self.data_path / snake(project_name)

        def do_new_project():
            target.mkdir(parents=True, exist_ok=True)
    
            from zipfile import ZipFile
            with ZipFile(template_zip, 'r') as f:
                f.extractall(path=target)
            if (m := (target / "__MACOSX")).exists():
                shutil.rmtree(m)
        
            original = "My Template"

            def pascal(s):
                return ''.join(s.split())

            def running(s):
                return ''.join(s.lower().split())

            for old, new in [
                (original, project_name),
                (pascal(original), pascal(project_name)),
                (running(original), running(project_name)),
                (snake(original), snake(project_name))
            ]:
                # Recursively scan files inside the newly extracted directory tree
                for file_path in target.rglob("*"):
                    
                    if file_path.is_file() and file_path.suffix in ['.py', '.toml', '.rst', '.md']:
                        # Read, replace token strings, and write back out safely
                        content = file_path.read_text(encoding="utf-8")
                        if old in content:
                            file_path.write_text(content.replace(old, new), encoding="utf-8")

                    if file_path.name == old:
                        file_path.rename(file_path.parent / new)
                    elif file_path.stem == old:
                        file_path.rename(file_path.parent / (new + file_path.suffix))
            asyncio.create_task(self.info(f"Created new project {project_name}"))

        if target.exists():
            asyncio.create_task(
                self.app.main_window.dialog(
                    toga.QuestionDialog(
                        "Folder Exists", 
                        f"Replace existing {snake(project_name)}?"
                    )
                )
            ).add_done_callback(
                lambda t: do_new_project() if t.result() else None
            )
        else:
            do_new_project()

    def start(self, s, m):
        print("Starting...")
        def script(spec, module):
            # Execute the module code so classes are defined
            try:
                spec.loader.exec_module(module)
                # Some modules need a nudge...
                if hasattr(module, "main"):
                    module.main()
            except Exception as e:
                self.app.loop.call_soon(lambda e=e: self.app.main_window.error_dialog("Script Failure", f"Script failed with: {str(e)}"))
            finally:
                self.app.loop.call_soon(lambda: self.script_activity.update(on=False)) 
        self.script_runner.run_student_script(lambda s=s, m=m: script(s, m))

    def handle_row_selection(self, widget):
        """Triggered automatically when an iOS row is tapped."""
        import importlib.util

        # Grab the currently selected row data dictionary
        selected_row = widget.selection
        if not selected_row:
            return

        # 1. Read the parsed dependency requirements array
        required_packages = getattr(selected_row, "dependencies", [])
        
        target_user_packages = self.data_path / "site_packages"
        
        # 2. Check and satisfy dependencies
        if required_packages:
            (pip.get_pip())(required_packages, target_user_packages)
        
        # 3. Proceed to mount the folder root and load the module
        import sys
        folder_path = str(selected_row.folder_root)
        if folder_path not in sys.path:
            sys.path.insert(0, folder_path)
        print(f"import path: {sys.path}") 
            
        # Clear out status title alterations and execute
        print(f"Launching {selected_row.title} from path: {selected_row.entry_point}")
        selected_file_path = Path(selected_row.entry_point)

        try:
            # Dynamically load the python module from an arbitrary path
            module_name = selected_file_path.parent.name
            spec = importlib.util.spec_from_file_location(module_name, selected_file_path, submodule_search_locations=(folder_path, selected_file_path.parent,))
            module = importlib.util.module_from_spec(spec)

            self.print_text.value = ""
            self.app.widgets["tabs"].current_tab = "Script"
            self.script_activity.update(f"Running {selected_row.title}")
            self.app.loop.call_soon(lambda s=spec, m=module: self.start(s, m))
        except Exception as e:
            self.app.main_window.error_dialog("Load Failure", f"Failed to execute script:\n{str(e)}")

    def clear_logs(self, widget=None):
        (self.data_path / "app_runtime.log").unlink()
        self.app.main_window.info_dialog("Logs Cleared", "You will need to close and re-open the app.")
    
    def tab_changed(self, widget):
        if t := widget.current_tab:
            match t.text:
                case "List":
                    self.reload_menu(self.app.widgets["script_list"])
                case "Logs":
                    self.reload_logs(widget) 

    def pad_keyboard(self, on):
        #keyboard_box.style.visibility = "visible" if on else "hidden"
        self.app.widgets["keyboard_box"].style.flex = 1 if on else 0

    def toggle_input(self, on):
        if on:
            self.app.widgets["script_box"].insert(0, self.input_box)
        elif self.input_box:
            self.app.widgets["script_box"].remove(self.input_box)
        self.pad_keyboard(on)

    def get_content(self):
        return toga.OptionContainer(
            id="tabs",
            content=[
                ("List", toga.Column(
                    children=[
                        toga.DetailedList(
                            id="script_list",
                            on_refresh=self.reload_menu,
                            on_select=self.handle_row_selection,
                            style=Pack(flex=1),
                            data=self.reload_menu()
                        )
                    ]
                ), self.icon_path / "list.png"),
                ("Script", toga.Column(
                    id="script_box",
                    children=[
                        toga.ScrollContainer(
                            horizontal=False,
                            content=self.print_text,
                            
                            style=Pack(flex=1)
                        ), 
                        toga.Box(
                            id="keyboard_box",
                            style=Pack(
                                flex=1, 
                                visibility="hidden"
                            ) 
                        ),
                        self.script_activity
                    ] 
                ), self.icon_path / "eye.png"), 
  
                ("Logs", toga.Column(
                    children=[
                        toga.ScrollContainer(
                            horizontal=False,
                            content=toga.MultilineTextInput(
                                readonly=True,
                                style=Pack(flex=1),
                                id="log_text",
                                value=self.reload_logs()),
                            style=Pack(flex=1)
                        ),
                        toga.Row(
                            children=[
                                toga.Button(
                                    "Reload",
                                    on_press=self.reload_logs,
                                    flex=1
                                ),
                                toga.Button(
                                    "Clear",
                                    on_press=self.clear_logs,
                                    flex=1
                                )
                            ]
                        )
                    ]
                ), self.icon_path / "log-file.png"),
                ("Setup", toga.Column(
                    children=[
                        toga.Row(
                            align_items="center",
                            children=[
                                toga.Label("New Project"),
                                toga.TextInput(id="new_project_name", flex=1, on_confirm=self.close_keyboard),
                                toga.Button("Add", on_press=self.new_project)
                            ]
                        ),
                        toga.Divider(),
                        toga.Button(
                            "Exit",
                            visibility="visible" if hasattr(self.app.main_window, "content_stack") and len(self.app.main_window.content_stack) > 0 else "hidden",
                        on_press=self.on_done_callback
                        )
                    ]), self.icon_path / "settings-sliders.png"),
                ("Help", toga.Row(
                     children=[
                         toga.WebView(
                             content=f"""
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; line-height: 1.6; padding: 20px; color: #333; }}
                code {{ background-color: #f6f8fa; padding: 2px 4px; border-radius: 3px; font-family: monospace; }}
                pre {{ background-color: #f6f8fa; padding: 16px; overflow: auto; border-radius: 6px; }}
                img {{ max-width: 100%; height: auto; }}
            </style>
        </head>
        <body>
                     {md(f.read_text() if (f := (self.template_path / "help.md")).exists() else "")}
        </body>
        </html>
""",
                             flex=1)]), self.icon_path / "interrogation.png")
            ],
            on_select=self.tab_changed
        )
