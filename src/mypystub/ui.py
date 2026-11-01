import asyncio
import io
import shutil
import sys
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from zipfile import ZIP_DEFLATED, ZipFile

import toga
from toga.style import Pack

from . import about, runner
from . import hooks as h
from . import piplike as pip
from . import settings as s
from .pages import help_html, html_page

UIUserInterfaceIdiomPad = 1

# Default list icons by scanned entry kind (see CREDITS.md). Missing files are
# skipped, so rows show no icon until the icon is downloaded.
# Top-level list rows: category name -> icon (see CREDITS.md). Missing icon files
# are skipped, so the rows show no icon until the icon is downloaded.
CATEGORY_ICONS = {
    "Examples": "examples.png",
    "Documents": "documents.png",
}

KIND_ICONS = {
    "folder": "folder.png",
    "project": "box.png",
    "script": "file-code.png",
}


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
        from toga_iOS.libs import NSURL, NSMutableArray

        from .bridge import UIActivityViewController

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

    def __init__(self, label_text: str, **kwargs):
        self.selection = toga.Selection(flex=1, **kwargs)
        super().__init__(
            direction="row",
            align_items="center",
            children=[
                toga.Label(label_text + ": "),
                self.selection,
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
        cast(Any, self.app).settings = s.Settings(host_app.paths)
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
        self.help_selection = LabelledSelection(
            "Show",
            items=["Help", "About"],
            on_change=self.show_help_page,
        )
        self.help_view = toga.WebView(flex=1)
        self.about_share = toga.Button(
            "Share", on_press=self.handle_about_share, visibility="hidden"
        )
        # Category being browsed (None: the list of categories), and the folder
        # within it, relative to the category's root
        self.category: str | None = None
        self.subfolder = Path()
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

    def clear_selection(self, widget: toga.DetailedList) -> None:
        """Deselect the tapped row once it has been read.

        toga_iOS never deselects a row, so after the list reloads (folder
        navigation, returning from a script) the old row stays selected and a
        later tap can read it instead of the row that was actually tapped.
        """
        if sys.platform == "ios":
            table = widget._impl.native
            if path := table.indexPathForSelectedRow:
                table.deselectRowAtIndexPath(path, animated=True)

    def reload_logs(self, widget: toga.Widget, **kwargs: Any) -> None:
        if log_path := getattr(sys.stdout, "path", None):
            logs = log_path.read_text()
            self.log_text.value = logs

    def category_dirs(self) -> dict[str, Path]:
        """The top-level categories: built-in examples and the user's Documents."""
        return {
            "Examples": self.this_path / "resources" / "examples",
            "Documents": Path(self.prototype_dir),
        }

    def get_category_dir(self) -> Path:
        assert self.category is not None
        return self.category_dirs()[self.category]

    def get_current_dir(self) -> Path:
        return self.get_category_dir() / self.subfolder

    def show_category(self, category: str | None) -> None:
        """Open a category at its root, or None for the list of categories."""
        self.category = category
        self.subfolder = Path()

    def bundled_icon(self, filename: str) -> toga.Image | None:
        """Load an icon from resources/icons, or None until the file is added."""
        path = self.icon_path / filename
        if not path.exists():
            return None
        image = toga.Image(path)
        if sys.platform == "ios":
            # The icons are black line art; tint them with the label colour so
            # they follow light and dark mode like the row text does
            from toga_iOS.libs import UIColor

            native = image._impl.native
            image._impl.native = native.imageWithTintColor(
                UIColor.labelColor(),
                renderingMode=1,  # UIImageRenderingModeAlwaysOriginal
            )
        return image

    def reload_menu(
        self, widget: toga.DetailedList | toga.Selection, **kwargs: Any
    ) -> None:
        # 0. At the top, the list is the categories themselves
        if self.category is None:
            self.script_list.data = [
                {
                    "title": name,
                    "subtitle": pip.folder_summary(path),
                    "icon": self.bundled_icon(CATEGORY_ICONS[name]),
                    "category": name,
                }
                for name, path in self.category_dirs().items()
            ]
            return

        # 1. Gather all of our TOML configuration profiles
        self.prototypes_data = pip.scan_all_prototypes(self.get_current_dir())

        # 2. Format the records specifically for Toga's DetailedList expectations
        up = self.bundled_icon("arrow-small-left.png")
        if self.subfolder != Path():
            where = f"{self.category}/{self.subfolder.as_posix()}"
            list_items = [
                {
                    "title": "..",
                    "subtitle": f"Up from {where}",
                    "icon": up,
                    "folder": self.get_current_dir().parent,
                }
            ]
        else:
            list_items = [
                {
                    "title": "..",
                    "subtitle": "Back to categories",
                    "icon": up,
                    "categories": True,
                }
            ]
        for proto in self.prototypes_data:
            # The prototype's own icon, if it set one and the file exists. Only
            # this is used as the Script view's splash; the small default icons
            # below are for the list alone and look poor stretched to a splash.
            own_icon = None
            if proto["icon_path"] and proto["icon_path"].exists():
                own_icon = toga.Image(
                    proto["icon_path"]
                )  # This should be Icon, but it works
            row_icon = own_icon
            icon_file = KIND_ICONS.get(proto.get("kind", ""))
            if row_icon is None and icon_file:
                row_icon = self.bundled_icon(icon_file)

            # Toga ignores the custom keys (entry_point, folder, ...) for rendering,
            # but holds onto them for callbacks!
            row = {k: v for k, v in proto.items() if k != "icon_path"}
            row["icon"] = row_icon
            row["splash"] = own_icon
            list_items.append(row)

        self.script_list.data = list_items

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

    def content_stack(self) -> runner.ObservableStack:
        """The window's takeover stack, upgraded so runs can watch it."""
        mw = self.app.main_window
        assert isinstance(mw, toga.MainWindow)
        stack = getattr(mw, "content_stack", None)
        if not isinstance(stack, runner.ObservableStack):
            stack = runner.ObservableStack(stack or [])
            mw.content_stack = stack  # pyright: ignore[reportAttributeAccessIssue]
        return stack

    def start(self, context: runner.RunContext) -> None:
        """Run a prototype on the script thread, like ``python script.py``.

        The run ends when the body returns, or, if it took over the window, when
        its takeover is popped off the content stack (see runner.RunLifetime).
        """
        print("Starting...")
        lifetime = runner.RunLifetime(
            self.content_stack(),
            self.app.loop.call_soon_threadsafe,
            lambda error: self.finish_run(context, error),
        )
        context.open()

        def script() -> None:
            error: BaseException | None = None
            try:
                context.run()
            except SystemExit as e:
                # sys.exit() / sys.exit(0) is a normal end, like at the terminal
                if e.code not in (None, 0):
                    error = e
            except BaseException as e:  # noqa: BLE001
                error = e
            finally:
                lifetime.body_finished(error)

        self.script_runner.run_student_script(script)

    def finish_run(
        self, context: runner.RunContext, error: BaseException | None
    ) -> None:
        """Restore process state, report any error, and tidy up the Script tab."""
        context.close()
        if error is None:
            self.end_script()
            return
        traceback.print_exception(error)

        async def report() -> None:
            message = (
                f"Script exited with status {error.code}"
                if isinstance(error, SystemExit)
                else f"Script failed with: {error!s}"
            )
            await self.error(message, "Script Failure")
            self.end_script()

        asyncio.create_task(report())

    async def handle_row_selection(
        self, widget: toga.DetailedList, **kwargs: Any
    ) -> None:
        """Triggered automatically when an iOS row is tapped."""
        # Grab the currently selected row data dictionary
        selected_row = widget.selection
        self.clear_selection(widget)
        if selected_row is None:
            return

        # Category rows, and ".." back to them, navigate instead of running
        if getattr(selected_row, "categories", False):
            self.show_category(None)
            self.reload_menu(widget)
            return
        if category := getattr(selected_row, "category", None):
            self.show_category(category)
            self.reload_menu(widget)
            return

        # Folder rows (including "..") navigate instead of running anything
        if folder := getattr(selected_row, "folder", None):
            self.subfolder = pip.relative_folder(self.get_category_dir(), folder)
            self.reload_menu(widget)
            return

        if not hasattr(selected_row, "entry_point"):
            return

        # 1. Read the parsed dependency requirements array
        required_packages = getattr(selected_row, "dependencies", [])

        target_user_packages = self.cache_path / "site_packages"
        if str(target_user_packages) not in sys.path:
            sys.path.insert(0, str(target_user_packages))

        # Switch to the Script view first, so installing dependencies shows
        # progress there instead of leaving the list looking frozen.
        title = getattr(selected_row, "title", "script")
        self.print_text.value = ""
        # Only a prototype's own icon is shown as a splash, never a default one
        if splash := getattr(selected_row, "splash", None):
            self.splash.image = splash
            self.splash.style.flex = 1
            self.script_scroll.style.flex = 0
        else:
            self.splash.image = None
            self.splash.style.flex = 0
            self.script_scroll.style.flex = 1
        self.app.widgets["tabs"].current_tab = "Script"
        self.script_activity.update(f"Preparing {title}")

        # 2. Check and satisfy dependencies
        if required_packages:
            # TODO Insert cache dir
            try:
                await pip.resolve_and_install_async(
                    required_packages,
                    target_user_packages,
                    on_progress=self.script_activity.update,
                )
            except Exception as e:  # noqa: BLE001
                # DependencyError, or e.g. an invalid requirement string
                traceback.print_exc()
                self.script_activity.update("Dependency install failed", on=False)
                await self.error(str(e), "Dependency Error")
                self.end_script()
                return

        # 3. Run it the way Python would: __main__, argv, its folder importable
        entry_point = Path(cast(Any, selected_row).entry_point)
        folder_root = Path(getattr(selected_row, "folder_root", entry_point.parent))
        print(f"Launching {title} from path: {entry_point}")
        try:
            if not entry_point.is_file():
                raise FileNotFoundError(f"Entry point not found: {entry_point}")
            context = runner.RunContext(runner.target_for(entry_point, folder_root))
        except Exception as e:  # noqa: BLE001
            self.script_activity.update(on=False)
            await self.error(f"Failed to execute script:\n{e!s}", "Load Failure")
            self.end_script()
            return

        self.script_activity.update(f"Running {title}")
        self.app.loop.call_soon(lambda: self.start(context))

    def clear_logs(self, widget: toga.Widget, **kwargs: Any) -> None:
        if log_path := getattr(sys.stdout, "path", None):
            log_path.unlink()
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
                case "Help":
                    self.show_help_page()

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

        except Exception as e:  # noqa: BLE001
            asyncio.create_task(
                self.error(
                    f"An error occurred while creating the archive: {e}",
                    "Backup Failed",
                )
            )

    def about_sections(self) -> list[about.Section]:
        paths = {
            "Documents": Path(self.data_path),
            "Data": Path(self.app.paths.data),
            "Cache": Path(self.cache_path),
            "Config": Path(self.app.paths.config),
        }
        return about.collect_environment(
            self.app.formal_name,
            self.app.version,
            paths,
            Path(self.cache_path) / "site_packages",
        )

    def show_help_page(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        if str(self.help_selection.value) == "About":
            body = about.to_html(self.about_sections())
            # open_share_sheet() is only implemented on iOS
            self.about_share.style.visibility = (
                "visible" if sys.platform == "ios" else "hidden"
            )
        else:
            help_md = self.template_path / "help.md"
            body = help_html(help_md.read_text()) if help_md.exists() else ""
            self.about_share.style.visibility = "hidden"
        self.help_view.content = html_page(body)

    def handle_about_share(self, widget: toga.Button, **kwargs: Any) -> None:
        try:
            report = Path(self.cache_path) / "about.txt"
            report.write_text(about.to_text(self.about_sections()), encoding="utf-8")
            open_share_sheet(widget, report)
        except Exception as e:  # noqa: BLE001
            asyncio.create_task(
                self.error(f"Could not share environment details: {e}", "Share")
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
                    toga.Column(children=[self.script_list]),
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
                    toga.Column(
                        children=[
                            self.help_selection,
                            self.help_view,
                            self.about_share,
                        ]
                    ),
                    self.icon_path / "interrogation.png",
                ),
            ],
            on_select=self.tab_changed,
        )
        self.show_help_page()
        self.app.loop.call_soon(lambda: self.reload_menu(self.script_list))
        return self.tabs
