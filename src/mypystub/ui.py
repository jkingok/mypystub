import asyncio
import importlib.util
import io
import shutil
import sys
import traceback
from collections.abc import Callable
from datetime import datetime
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from typing import Any, cast
from zipfile import ZIP_DEFLATED, ZipFile

import toga
from markdown import markdown as md
from toga.style import Pack

from . import hooks as h
from . import piplike as pip
from . import settings as s

UIUserInterfaceIdiomPad = 1


def is_ipad_from_window(toga_window: toga.Window) -> bool:
    """Detects iPad idiom via the native UIWindow / UIViewController trait collection."""
    # Toga's underlying UIKit native object (UIWindow or UIViewController)
    return (
        sys.platform == "ios"
        and toga_window._impl.native.traitCollection.userInterfaceIdiom
        == UIUserInterfaceIdiomPad
    )  # pyright: ignore[reportPrivateUsage]


def zip_directory_to_bytes(source_dir: Path) -> bytes:
    """Recursively archives a directory into a zip file stored in memory as bytes."""
    zip_buffer = io.BytesIO()

    if source_dir.exists():
        with ZipFile(zip_buffer, "w", ZIP_DEFLATED) as zip_file:
            # rglob("*") grabs everything recursively
            for item in source_dir.rglob("*"):
                if item.is_file():
                    # relative_to ensures we don't include absolute iOS system paths
                    archive_name = item.relative_to(source_dir)
                    zip_file.write(item, archive_name)

    return zip_buffer.getvalue()


def create_nested_app_backup(app: toga.App) -> Path:
    """
    Creates a master backup zip containing data.zip and config.zip in memory,
    then writes the master file out to the app's cache directory.

    Args:
        app: The running toga.App instance (e.g., self inside an app class)

    Returns:
        Path: The location of the final master zip file on disk.
    """
    # 1. Resolve Toga's native paths
    cache_dir = app.paths.cache
    config_dir = app.paths.config
    data_dir = getattr(app, "user_documents_dir", app.paths.data)

    # 2. Build sub-archives in memory as bytes
    print(f"Archiving cache directory: {cache_dir}")
    cache_zip_bytes = zip_directory_to_bytes(cache_dir)

    print(f"Archiving config directory: {config_dir}")
    config_zip_bytes = zip_directory_to_bytes(config_dir)

    print(f"Archiving data directory: {data_dir}")
    data_zip_bytes = zip_directory_to_bytes(data_dir)

    # 3. Create the master zip filename using the app's identifier and timestamp
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    master_filename = f"{app.formal_name.lower().replace(' ', '_')}-{timestamp}.zip"

    # We write the final file to the app's cache directory (safe for transient shares)
    master_zip_path = app.paths.cache / master_filename
    app.paths.cache.mkdir(parents=True, exist_ok=True)

    # 4. Pack the memory archives into the final master zip on disk
    with ZipFile(master_zip_path, "w", ZIP_DEFLATED) as master_zip:
        # writestr allows passing raw bytes and assigning an internal archive filename
        master_zip.writestr("cache.zip", cache_zip_bytes)
        master_zip.writestr("config.zip", config_zip_bytes)
        master_zip.writestr("data.zip", data_zip_bytes)

    print(f"Structured master archive created at: {master_zip_path}")
    return master_zip_path


def open_share_sheet(w: toga.Widget, file_path: Path) -> None:
    """
    Opens the iOS native share sheet for a specific HTML file.

    :param w: The active Toga widget instance initiating the share.
    :param file_path: Absolute string path to the local file.
    """
    if sys.platform == "ios":
        from rubicon.objc import ObjCClass

        # Load the required Objective-C classes
        UIActivityViewController = ObjCClass("UIActivityViewController")
        NSURL = ObjCClass("NSURL")
        NSMutableArray = ObjCClass("NSMutableArray")
        # 1. Ensure the file path exists and convert it into a native file URL
        absolute_path = str(file_path.resolve())
        file_url = NSURL.fileURLWithPath_(absolute_path)

        # 2. Add the URL asset into an Objective-C array of items to share
        share_items = NSMutableArray.alloc().init()
        share_items.addObject_(file_url)

        # 3. Initialize the native UIActivityViewController
        # Pass None for custom applicationActivities to use standard system defaults
        activity_vc = UIActivityViewController.alloc().initWithActivityItems(
            share_items, applicationActivities=None
        )

        # 4. Grab the native UIViewController backing your Toga Window
        if w.app and w.app.main_window:
            assert isinstance(w.app.main_window, toga.MainWindow)
            presenting_vc = w.app.main_window._impl.native.rootViewController

            # 5. Handle iPad popover configurations safely to prevent crashes
            if activity_vc.popoverPresentationController:
                # Anchor the popover menu to the center or bounds of the current view frame
                activity_vc.popoverPresentationController.sourceView = (
                    presenting_vc.view
                )
                activity_vc.popoverPresentationController.sourceRect = (
                    presenting_vc.view.bounds
                )
                # Optional: restrict arrow directions if needed
                # activity_vc.popoverPresentationController.permittedArrowDirections = 0

            # 6. Present the share sheet asynchronously over the top of the interface
            presenting_vc.presentViewController(
                activity_vc, animated=True, completion=None
            )


class LabelledProgress(toga.Box):
    def __init__(self, **kwargs: Any) -> None:
        self.bar = toga.ProgressBar(flex=1)
        self.text = toga.Label("")
        super().__init__(direction="row", children=[self.bar, self.text], **kwargs)

    def start(self, limit: int = 0) -> None:
        self.bar.max = limit if limit > 0 else None
        self.bar.start()
        self.update(0)

    def update(self, value: int) -> None:
        if self.bar.max:
            if self.bar.max == 100:
                self.text.text = f"{value}%"
            else:
                self.text.text = f"{value}/{self.bar.max}"
        else:
            self.text.text = ""
        self.bar.value = value

    def stop(self) -> None:
        if self.bar.max:
            self.update(int(self.bar.max))
        self.bar.stop()


class LabelledActivity(toga.Box):
    def __init__(self, **kwargs) -> None:
        self.activity = toga.ActivityIndicator()
        self.text = toga.Label("", flex=1)
        super().__init__(direction="row", children=[self.activity, self.text], **kwargs)

    def update(self, value: str = "", on: bool = True) -> None:
        self.activity.start() if on else self.activity.stop()
        self.text.text = value


class NotAnOptionContainer(toga.Box):
    class CurrentTab:
        def __init__(self, text: str) -> None:
            self.text = text

    def __init__(
        self,
        content: toga.Widget,
        on_select: Callable[[toga.Widget], None] | None = None,
        **kwargs: Any,
    ) -> None:
        self.content = content
        self.on_selected = on_select
        super().__init__(
            direction="column",
            children=[
                toga.Column(flex=1),
                toga.Row(
                    children=[
                        toga.Button(tab[0], on_press=self.swap_in, flex=1)  # type: ignore[arg-type]
                        for tab in content
                    ]
                ),
            ],
            **kwargs,
        )
        self.swap_in_name(self.content[0][0])

    def swap_in_name(self, t: str) -> None:
        for tab in self.content:
            if tab[0] == t:
                tab[1].style.flex = 1
                self.replace(self.children[0], tab[1])
                self._current_tab = NotAnOptionContainer.CurrentTab(t)
                if self.on_selected:
                    self.on_selected(self)
                break

    def swap_in(self, w: toga.Button, **kwargs: Any) -> None:
        self.swap_in_name(w.text)

    @property
    def current_tab(self) -> CurrentTab:
        return self._current_tab

    @current_tab.setter
    def current_tab(self, value: str) -> None:
        self.swap_in_name(value)

class LabelledSelection(toga.Box):
    """
    Toga Box combining a text Label and Selection dropdown widget.

    :param label_text: Label text prefix.
    :type label_text: str
    :param value_text: Initially selected item value.
    :type value_text: str
    :param value_list: List of available selection items.
    :type value_list: list
    :param callback: Change event callback handler.
    :type callback: callable
    :param id: Widget identifier.
    :type id: str
    """

    def __init__(
        self, label_text: str, on_press=None, **kwargs
    ):
        self.selection = toga.Selection(flex=1, **kwargs)
        self.on_press = on_press
        super().__init__(
            direction="row",
            align_items="center",
            children=[
                toga.Label(label_text + ": "),
                self.selection,
                toga.Button(
                    "⤵️",
                    on_press=lambda w: (self.selection._impl.native.resignFirstResponder(), self.on_press(w) if self.on_press else None)
                )
            ],
        )

    @property
    def value(self):
        return self.selection.value


class Prototype:
    def __init__(self, host_app: toga.App, on_done: Callable[[Any], None]) -> None:
        self.app = host_app
        self.on_done_callback = on_done  # This is your ticket back to safety
        self.title = "Launcher"  # host_app.formal_name
        self.app.settings = s.Settings(host_app.paths) # pyright: ignore [reportAttributeAccessIssue]
        self.cache_path = self.app.paths.cache
        self.data_path = getattr(self.app, "user_documents_dir", self.app.paths.data)
        print(f"Prototype initialized with data_path: {self.data_path}")
        self.this_path = Path(__file__).resolve().parent
        self.icon_path = self.this_path / "resources" / "icons"
        self.template_path = self.this_path / "resources" / "templates"
        self.prototype_dir = self.data_path
        self.input_prompt = toga.Label("Input")
        self.input_text = toga.TextInput(
            style=Pack(flex=1),
            on_gain_focus=self.gain_focus,
            on_lose_focus=self.lose_focus,
        )
        self.input_box = toga.Column(
            children=[self.input_prompt, self.input_text], text_align="center"
        )
        self.print_text = toga.MultilineTextInput(readonly=True)
        self.script_runner = h.ScriptRunner(
            host_app,
            self.input_prompt,
            self.input_text,
            self.print_text,
            self.toggle_input,
            self.toggle_print,
        )
        self.script_scroll = toga.ScrollContainer(
            horizontal=False, content=self.print_text, style=Pack(flex=1)
        )
        self.script_activity = LabelledActivity()
        self.splash = toga.ImageView(style=Pack(flex=0))
        self.dir_selection = LabelledSelection("Category", items=["Examples", "User"], on_change=lambda w: setattr(self.script_list, "data", None), on_press=self.reload_menu)
        self.script_list = toga.DetailedList(
            on_refresh=self.reload_menu,
            on_select=self.handle_row_selection,
            style=Pack(flex=1),
            # data=self.reload_menu()
        )
        self.log_text = toga.MultilineTextInput(
            readonly=True,
            style=Pack(flex=1),
        )

    async def todo(self, name: str) -> None:
        assert isinstance(self.app.main_window, toga.MainWindow)
        await self.app.main_window.dialog(toga.InfoDialog("TODO", name))

    async def info(self, text: str, title: str | None = None) -> None:
        assert isinstance(self.app.main_window, toga.MainWindow)
        await self.app.main_window.dialog(
            toga.InfoDialog(title if title else "Info", text)
        )

    async def error(self, text: str, title: str | None = None) -> None:
        assert isinstance(self.app.main_window, toga.MainWindow)
        await self.app.main_window.dialog(
            toga.ErrorDialog(title if title else "Error", text)
        )

    async def question(
        self,
        text: str,
        title: str | None = None,
        positive: Callable[[], None] | None = None,
        negative: Callable[[], None] | None = None,
    ) -> None:
        assert isinstance(self.app.main_window, toga.MainWindow)
        if await self.app.main_window.dialog(
            toga.QuestionDialog(title if title else "Question", text)
        ):
            if positive:
                positive()
        else:
            if negative:
                negative()

    def close_keyboard(self, widget: toga.TextInput, **kwargs: Any) -> None:
        """Triggered when the user presses 'Return' or 'Done' on the iPad keyboard."""
        # Dismiss the keyboard by resigning First Responder status
        # Check if we are running on iOS/iPadOS via the native implementation handle
        if sys.platform == "ios":
            widget._impl.native.resignFirstResponder()

    def reload_logs(self, widget: toga.Widget, **kwargs: Any) -> None:
        if sys.stdout and hasattr(sys.stdout, "path"):
            logs = sys.stdout.path.read_text() # pyright: ignore [reportAttributeAccessIssue]
            self.log_text.value = logs

    def get_current_dir(self) -> Path:
        match str(self.dir_selection.value):
            case "Examples":
                return self.this_path / "resources" / "examples"
            case _:
                return self.prototype_dir 

    def reload_menu(self, widget: toga.DetailedList | toga.Selection, **kwargs: Any) -> None:
        # 1. Gather all of our TOML configuration profiles
        self.prototypes_data = pip.scan_all_prototypes(self.get_current_dir())

        # 2. Format the records specifically for Toga's DetailedList expectations
        list_items = []
        for proto in self.prototypes_data:
            # Safely build a toga.Image if an icon path was specified and exists
            row_icon = None
            if proto["icon_path"] and proto["icon_path"].exists():
                row_icon = toga.Image(
                    proto["icon_path"]
                )  # This should be Icon, but it works

            list_items.append(
                {
                    "title": proto["title"],
                    "subtitle": proto["subtitle"],
                    "icon": row_icon,
                    # Toga ignores these custom keys for rendering, but holds onto them for callbacks!
                    "entry_point": proto["entry_point"],
                    "folder_root": proto["folder_root"],
                    "dependencies": proto["dependencies"],
                }
            )

        widget.data = list_items  # type: ignore[assignment]

    def new_project(self, widget: toga.Button, **kwargs: Any) -> None:
        def snake(s: str) -> str:
            return "_".join(s.lower().split())

        project_name = self.app.widgets["new_project_name"].value
        template_zip = self.template_path / "my_template.zip"
        target = self.data_path / snake(project_name)

        def do_new_project() -> None:
            target.mkdir(parents=True, exist_ok=True)

            from zipfile import ZipFile

            with ZipFile(template_zip, "r") as f:
                f.extractall(path=target)
            if (m := (target / "__MACOSX")).exists():
                shutil.rmtree(m)

            original = "My Template"

            def pascal(s: str) -> str:
                return "".join(s.split())

            def running(s: str) -> str:
                return "".join(s.lower().split())

            for old, new in [
                (original, project_name),
                (pascal(original), pascal(project_name)),
                (running(original), running(project_name)),
                (snake(original), snake(project_name)),
            ]:
                # Recursively scan files inside the newly extracted directory tree
                for file_path in target.rglob("*"):

                    if file_path.is_file() and file_path.suffix in [
                        ".py",
                        ".toml",
                        ".rst",
                        ".md",
                    ]:
                        # Read, replace token strings, and write back out safely
                        content = file_path.read_text(encoding="utf-8")
                        if old in content:
                            file_path.write_text(
                                content.replace(old, new), encoding="utf-8"
                            )

                    if file_path.name == old:
                        file_path.rename(file_path.parent / new)
                    elif file_path.stem == old:
                        file_path.rename(file_path.parent / (new + file_path.suffix))
            asyncio.create_task(self.info(f"Created new project {project_name}"))

        if target.exists():
            asyncio.create_task(
                self.question(
                    f"Replace existing {snake(project_name)}?",
                    "Folder Exists",
                    do_new_project,
                )
            )
        else:
            do_new_project()

    def end_script(self) -> None:
        self.script_activity.update(on=False)
        self.splash.image = None
        if not self.print_text.value:
            self.tabs.current_tab = "List"

    def start(self, s: ModuleSpec, m: ModuleType) -> None:
        print("Starting...")

        def script(spec: ModuleSpec, module: ModuleType) -> None:
            # Execute the module code so classes are defined
            try:
                if spec and spec.loader:
                    spec.loader.exec_module(module)
                # Some modules need a nudge...
                if hasattr(module, "main"):
                    module.main()
            except Exception as e: # noqa: BLE001
                asyncio.run_coroutine_threadsafe(
                    self.error(f"Script failed with: {e!s}", "Script Failure"),
                    self.app.loop,
                )
            finally:
                self.app.loop.call_soon_threadsafe(self.end_script)

        self.script_runner.run_student_script(
            cast(Callable[[], None], lambda s=s, m=m: script(s, m))
        )

    async def handle_row_selection(self, widget: toga.DetailedList, **kwargs: Any) -> None:
        """Triggered automatically when an iOS row is tapped."""
        # Grab the currently selected row data dictionary
        selected_row = widget.selection
        if selected_row is None or not hasattr(selected_row, "entry_point"):
            return

        # 1. Read the parsed dependency requirements array
        required_packages = getattr(selected_row, "dependencies", [])

        target_user_packages = self.cache_path / "site_packages"

        # 2. Check and satisfy dependencies
        if required_packages:
            # TODO Insert cache dir
            # TODO Track the progress as it happens
            try:
                await pip.resolve_and_install_async(required_packages, target_user_packages)
            except pip.DependencyError as de:
                traceback.print_exc()
                await self.error(str(de), "Dependency Error")
                return

        # 3. Proceed to mount the folder root and load the module
        import sys

        folder_path = str(getattr(selected_row, "folder_root", Path(".")).resolve())
        if folder_path not in sys.path:
            sys.path.insert(0, folder_path)
        print(f"import path: {sys.path}")

        # Clear out status title alterations and execute
        print(f"Launching {getattr(selected_row, "title", "?")} from path: {getattr(selected_row, "entry_point", "?")}")
        selected_file_path = Path(selected_row.entry_point) # pyright: ignore [reportAttributeAccessIssue]

        try:
            # Dynamically load the python module from an arbitrary path
            module_name = selected_file_path.parent.name
            spec = importlib.util.spec_from_file_location(
                module_name,
                selected_file_path,
                submodule_search_locations=[
                    folder_path,
                    str(selected_file_path.parent),
                ],
            )
            if spec:
                module = importlib.util.module_from_spec(spec)

                self.print_text.value = ""
                if icon := getattr(selected_row, "icon", None):
                    self.splash.image = icon
                    self.splash.style.flex = 1
                    self.script_scroll.style.flex = 0
                self.app.widgets["tabs"].current_tab = "Script"
                self.script_activity.update(
                    f"Running {getattr(selected_row, 'title', "script")}"
                )
                self.app.loop.call_soon(
                    cast(Callable[[], None], lambda s=spec, m=module: self.start(s, m))
                )
        except Exception as e: # noqa: BLE001
            asyncio.create_task(
                self.error(f"Failed to execute script:\n{e!s}", "Load Failure")
            )

    def clear_logs(self, widget: toga.Widget, **kwargs: Any) -> None:
        if sys.stdout and hasattr(sys.stdout, "path"):  
            sys.stdout.path.unlink() # pyright: ignore [reportAttributeAccessIssue]
            self.log_text.value = ""
            asyncio.create_task(
                self.info("You will need to close and re-open the app.", "Logs Cleared")
            )

    def tab_changed(self, widget: toga.Widget) -> None:
        if t := widget.current_tab:
            match t.text:
                case "List":
                    self.reload_menu(self.script_list)
                case "Logs":
                    self.reload_logs(widget)

    def pad_keyboard(self, on: bool) -> None:
        # keyboard_box.style.visibility = "visible" if on else "hidden"
        self.app.widgets["keyboard_box"].style.flex = 1 if on else 0

    def gain_focus(self, widget: toga.TextInput, **kwargs: Any) -> None:
        self.pad_keyboard(True)

    def lose_focus(self, widget: toga.TextInput, **kwargs: Any) -> None:
        self.pad_keyboard(False)

    def toggle_input(self, on: bool) -> None:
        if on:
            self.app.widgets["script_box"].insert(0, self.input_box)
        elif self.input_box:
            self.app.widgets["script_box"].remove(self.input_box)
        self.pad_keyboard(on)

    def toggle_print(self, on: bool) -> None:
        if on:
            self.splash.style.flex = 0
            self.script_scroll.style.flex = 1

    # Inside your Toga App class layout or commands:
    def handle_backup_press(self, widget: toga.Button, **kwargs: Any) -> None:
        try:
            # 1. Build the nested structured zip
            backup_file = create_nested_app_backup(self.app)

            # 2. Open native iOS Share Sheet via Rubicon-ObjC
            open_share_sheet(widget, backup_file)

        except Exception as e: # noqa: BLE001
            asyncio.create_task(
                self.error(
                    f"An error occurred while creating the archive: {e}",
                    "Backup Failed",
                )
            )

    def handle_wipe_cache(self, widget: toga.Button, **kwargs: Any) -> None:
        for f in Path(self.app.paths.cache).iterdir():
            print(f)

    def choose_container(self, *args: Any, **kwargs: Any) -> toga.Widget:
        assert isinstance(self.app.main_window, toga.MainWindow)
        if is_ipad_from_window(self.app.main_window):
            return NotAnOptionContainer(*args, **kwargs)
        else:
            return toga.OptionContainer(*args, **kwargs)

    def do_on_done_callback(self, widget: toga.Widget, **kwargs: Any) -> None:
        self.on_done_callback(widget)

    def get_content(self) -> toga.Widget:
        # return toga.OptionContainer(
        self.tabs = self.choose_container(
            id="tabs",
            content=[
                (
                    "List",
                    toga.Column(children=[self.dir_selection, self.script_list]),
                    self.icon_path / "list.png",
                ),
                (
                    "Script",
                    toga.Column(
                        id="script_box",
                        children=[
                            self.splash,
                            self.script_scroll,
                            toga.Box(id="keyboard_box", style=Pack(flex=0)),
                            self.script_activity,
                        ],
                    ),
                    self.icon_path / "eye.png",
                ),
                (
                    "Logs",
                    toga.Column(
                        children=[
                            toga.ScrollContainer(
                                horizontal=False,
                                content=self.log_text,
                                style=Pack(flex=1),
                            ),
                            toga.Row(
                                children=[
                                    toga.Button(
                                        "Reload", on_press=self.reload_logs, flex=1
                                    ),
                                    toga.Button(
                                        "Clear", on_press=self.clear_logs, flex=1
                                    ),
                                ]
                            ),
                        ]
                    ),
                    self.icon_path / "log-file.png",
                ),
                (
                    "Setup",
                    toga.Column(
                        children=[
                            toga.Row(
                                align_items="center",
                                children=[
                                    toga.Label("New Project"),
                                    toga.TextInput(
                                        id="new_project_name",
                                        flex=1,
                                        on_confirm=self.close_keyboard,
                                    ),
                                    toga.Button("Add", on_press=self.new_project),
                                ],
                            ),
                            toga.Divider(),
                            toga.Button("Backup", on_press=self.handle_backup_press),
                            toga.Button("Wipe Cache", on_press=self.handle_wipe_cache),
                            toga.Divider(),
                            toga.Button(
                                "Exit",
                                visibility=(
                                    "visible"
                                    if hasattr(self.app.main_window, "content_stack")
                                    and len(
                                        getattr(
                                            self.app.main_window, "content_stack", []
                                        )
                                    )
                                    > 0
                                    else "hidden"
                                ),
                                on_press=self.do_on_done_callback,
                            ),
                        ]
                    ),
                    self.icon_path / "settings-sliders.png",
                ),
                (
                    "Help",
                    toga.Row(
                        children=[
                            toga.WebView(
                                content=f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <!-- Configures iOS viewport: sets width, prevents horizontal scroll, and fits notch/home indicator areas -->
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  
  <!-- Informs the browser that the site supports both light and dark system themes -->
  <meta name="color-scheme" content="light dark">
  
  <title>Embedded Content</title>

  <style>
    /* CSS Variables using light-dark() to switch automatically based on system preference */
    :root {{
      color-scheme: light dark;
      --bg-color: light-dark(#ffffff, #121212);
      --text-color: light-dark(#1c1c1e, #f2f2f7);
      --card-bg: light-dark(#f2f2f7, #1c1c1e);
      --border-color: light-dark(#e5e5ea, #3a3a3c);
    }}

    /* Prevent accidental horizontal overflow */
    *, *::before, *::after {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      padding: 0;
      background-color: var(--bg-color);
      color: var(--text-color);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.5;
      
      /* Ensures text wraps properly when zoomed */
      overflow-wrap: break-word;
      word-break: break-word;
    }}

    /* Images scale down to fit container width, preventing layout break on zoom */
    img, video, svg {{
      max-width: 100%;
      height: auto;
    }}
  </style>
</head>
<body>
    {md(f.read_text() if (f := (self.template_path / "help.md")).exists() else "")}
</body>
</html>
""",
                                flex=1,
                            )
                        ]
                    ),
                    self.icon_path / "interrogation.png",
                ),
            ],
            on_select=self.tab_changed,
        )
        self.app.loop.call_soon(lambda: self.reload_menu(self.script_list))
        return self.tabs
