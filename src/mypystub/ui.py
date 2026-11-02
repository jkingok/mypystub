import asyncio
import importlib
import io
import platform
import shutil
import sys
import traceback
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, cast
from zipfile import ZIP_DEFLATED, ZipFile

import httpx2
import toga
from toga.style import Pack

from . import (
    about,
    info_pages,
    maintenance,
    permissions,
    row_info,
    runner,
    setup_pages,
)
from . import hooks as h
from . import piplike as pip
from . import settings as s
from .pages import help_html, html_page, readme_html
from .run_settings import Layer, RunSettings, merged_env, settings_key
from .run_with import RunWithForm
from .widgets import OrientationBox

UIUserInterfaceIdiomPad = 1

# Text colour for a run's stderr: an orange that reads as a warning, with
# enough contrast on both the light and the dark background
WARNING_COLOUR = "#d9480f"

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
    "package": "boxes.png",  # a project with several entry points
    "script": "file-code.png",
}

# Entry points inside a package, by kind. Placeholders until the icons are
# added: a missing file shows no icon (see bundled_icon).
ENTRY_ICONS = {
    "cli": "terminal.png",
    "gui": "window.png",
    "other": "plug.png",
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
    """A row of tab buttons standing in for OptionContainer on iPad.

    toga-iOS's OptionContainer becomes iPadOS's floating tab bar, but the tabs'
    content isn't laid out below it: the list's first row hides under the bar,
    and Help and Setup come out blank (checked on iPadOS 27, #112). So iPad
    gets this instead. It looks like a tab bar: each button has its tab's
    icon, and the selected tab is bold in the accent colour while the others
    are grey.
    """

    # Points: a tab bar icon's size, and room for an iPad window's corner grip
    ICON_SIZE = 24
    RESIZE_HANDLE = 24
    UNSELECTED = "gray"

    class CurrentTab:
        """The selected tab, shaped like OptionContainer's (``.text``)."""

        def __init__(self, text: str) -> None:
            """Name the selected tab."""
            self.text = text

    def __init__(
        self,
        content: Sequence[tuple[str, toga.Widget, Path | None]],
        on_select: Callable[[toga.Widget], None] | None = None,
        **kwargs: Any,
    ) -> None:
        """Build the row from OptionContainer-style (title, content, icon) tabs."""
        self.content = list(content)
        self.on_selected = on_select
        self.icons: dict[str, toga.Icon] = {}
        self.buttons = [self.tab_button(title, icon) for title, _, icon in self.content]
        self.tab_row = toga.Row(
            children=list(self.buttons),
            margin_right=self.RESIZE_HANDLE,
            margin_bottom=4,
        )
        super().__init__(
            direction="column",
            children=[toga.Column(flex=1), self.tab_row],
            **kwargs,
        )
        self.swap_in_name(self.content[0][0])

    def tab_button(self, title: str, icon_path: Path | None) -> toga.Button:
        """One tab's button, remembering its icon if the file exists.

        Toga won't put both text and an icon on a button, so the icon is
        kept here and drawn beside the title natively (see _show_icon).
        """
        button = toga.Button(title, on_press=self.swap_in, flex=1)
        if icon_path is not None and Path(icon_path).exists():
            self.icons[title] = toga.Icon(icon_path)
        return button

    def show_selected(self, title: str) -> None:
        """Mark the selected tab: bold in the accent colour; others grey."""
        for button in self.buttons:
            selected = button.text == title
            # Tint first: toga-iOS draws a reset title colour in the tint
            self._show_icon(button, selected)
            button.style.font_weight = "bold" if selected else "normal"
            if selected:
                del button.style.color  # the accent colour, as Toga draws it
            else:
                button.style.color = self.UNSELECTED

    def _show_icon(self, button: toga.Button, selected: bool) -> None:
        """On iOS, draw the tab's icon beside its title, tinted like it.

        The icons are black line art, which would vanish in dark mode, so each
        is drawn as a template at tab bar size: the accent colour when
        selected, grey otherwise, and dimmed by UIKit when disabled.
        """
        if sys.platform != "ios":
            return
        from toga_iOS.libs import UIColor, UIControlStateNormal

        icon = self.icons.get(str(button.text))
        if icon is None:
            return
        native = button._impl.native
        image = icon._impl._as_size(self.ICON_SIZE).imageWithRenderingMode(
            2  # UIImageRenderingModeAlwaysTemplate
        )
        native.setImage(image, forState=UIControlStateNormal)
        # The same grey as the title (UNSELECTED); None inherits the accent
        native.tintColor = None if selected else UIColor.grayColor

    def swap_in_name(self, t: str) -> None:
        """Show the tab titled `t`, and report the change."""
        for tab in self.content:
            if tab[0] == t:
                tab[1].style.flex = 1
                self.replace(self.children[0], tab[1])
                self._current_tab = NotAnOptionContainer.CurrentTab(t)
                self.show_selected(t)
                if self.on_selected:
                    self.on_selected(self)
                break

    def swap_in(self, w: toga.Button, **kwargs: Any) -> None:
        """A tab button was pressed."""
        self.swap_in_name(str(w.text))

    @property
    def current_tab(self) -> CurrentTab:
        """The selected tab."""
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
        # The run's stderr, shown beside or below its output (#119). It's
        # hidden until something is written to it, and Hide hides it again
        # until the next write.
        self.error_text = toga.MultilineTextInput(
            readonly=True, color=WARNING_COLOUR, flex=1
        )
        self.error_pane = toga.Column(
            display="none",
            children=[
                toga.Row(
                    align_items="center",
                    margin=(0, 4),
                    children=[
                        toga.Label("Errors and warnings", color=WARNING_COLOUR, flex=1),
                        toga.Button("Hide", on_press=self.hide_errors),
                    ],
                ),
                self.error_text,
            ],
        )
        self.script_runner = h.ScriptRunner(
            host_app,
            self.input_prompt,
            self.input_text,
            self.print_text,
            self.toggle_input,
            self.toggle_print,
            on_error_output=self.show_error_output,
        )
        self.script_scroll = toga.ScrollContainer(
            horizontal=False, content=self.print_text, style=Pack(flex=1)
        )
        self.script_output = OrientationBox(self.script_scroll, self.error_pane)
        self.script_activity = LabelledActivity()
        # Each run gets an id; end-of-run work for an older run is ignored (#64)
        self.run_id = 0
        self.ended_run = 0
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
        # Setup view (#77): a menu of sections, each opening a detail page (a
        # WebView, since Labels don't wrap) with native buttons for its actions
        self.setup_view = toga.WebView(flex=1)
        self.setup_page: str | None = None
        self.setup_html = ""
        self.update_all_button = toga.Button(
            "Update all", on_press=self.handle_update_all, enabled=False
        )
        self.setup_activity = LabelledActivity()
        self.packages_summary = ""
        self.pending_updates: list[maintenance.Update] = []
        # None until checked; the last check's error, if it failed
        self.checked_updates: list[maintenance.Update] | None = None
        self.update_error: str | None = None
        self.health: maintenance.Health | None = None
        self.health_error: str | None = None
        # Category being browsed (None: the list of categories), and the folder
        # within it, relative to the category's root
        self.category: str | None = None
        self.subfolder = Path()
        # A package with several entry points that's open, listing them
        self.package_dir: Path | None = None
        # Content-stack depths under each screen pushed by push_screen()
        self.screen_bases: list[int] = []
        # Toga's swipe actions are the same for every row (#59): swipe left
        # for Info, swipe right for Setup
        self.script_list = toga.DetailedList(
            on_refresh=self.reload_menu,
            on_select=self.handle_row_selection,
            primary_action="Info",
            on_primary_action=self.handle_info,
            secondary_action="Setup",
            on_secondary_action=self.handle_run_with,
            style=Pack(flex=1),
        )
        self.log_text = toga.MultilineTextInput(
            readonly=True,
            style=Pack(flex=1),
        )

    async def todo(self, name: str) -> None:
        assert isinstance(self.app.main_window, toga.MainWindow)
        await self.app.main_window.dialog(toga.InfoDialog("TODO", name))

    async def ask(self, title: str, text: str) -> bool:
        """Ask a yes/no question; True for yes."""
        assert isinstance(self.app.main_window, toga.MainWindow)
        return bool(await self.app.main_window.dialog(toga.QuestionDialog(title, text)))

    async def tell(self, title: str, text: str) -> None:
        """Show a message (the title first, for the Setup form)."""
        await self.info(text, title)

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
        self.package_dir = None

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

        if self.package_dir is not None:
            self.script_list.data = self.package_rows(self.package_dir)
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

    def current_folder_name(self) -> str:
        """The folder being browsed, as messages name it."""
        if self.subfolder == Path():
            return str(self.category)
        return f"{self.category}/{self.subfolder.as_posix()}"

    def package_rows(self, package_dir: Path) -> list[dict[str, Any]]:
        """The rows inside an open package: ".." and its entry points."""
        package = pip.scan_project(package_dir)
        rows: list[dict[str, Any]] = [
            {
                "title": "..",
                "subtitle": f"Back to {self.current_folder_name()}",
                "icon": self.bundled_icon("arrow-small-left.png"),
                "package_up": True,
            }
        ]
        for row in pip.entry_rows(package) if package["kind"] == "package" else []:
            row.pop("icon_path")
            row["icon"] = self.bundled_icon(ENTRY_ICONS[row["entry"].kind])
            row["splash"] = None
            rows.append(row)
        return rows

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

    def end_script(self, run_id: int | None = None) -> None:
        """Tidy up after a run: back to the list unless there's output to read.

        Tabs only change while the launcher is on screen; if a takeover is still
        showing, they're left alone (#64, case C).
        """
        self.splash.image = None
        action = runner.end_action(printed=self.script_runner.printed, error=False)
        if action == "stay":
            self.script_activity.update("Finished", on=False)
        else:
            self.script_activity.update(on=False)
            if self.tabs.window is not None:
                self.tabs.current_tab = "List"
        self.ended_run = self.run_id if run_id is None else run_id

    def content_stack(self) -> runner.ObservableStack:
        """The window's takeover stack, upgraded so runs can watch it."""
        mw = self.app.main_window
        assert isinstance(mw, toga.MainWindow)
        stack = getattr(mw, "content_stack", None)
        if not isinstance(stack, runner.ObservableStack):
            stack = runner.ObservableStack(stack or [])
            mw.content_stack = stack  # pyright: ignore[reportAttributeAccessIssue]
        stack.window = mw
        return stack

    def start(self, context: runner.RunContext) -> None:
        """Run a prototype on the script thread, like ``python script.py``.

        The run ends when the body returns, or, if it took over the window, when
        its takeover is popped off the content stack (see runner.RunLifetime).
        """
        print("Starting...")
        self.run_id += 1
        run_id = self.run_id
        stack = self.content_stack()
        # A takeover's extra Back can't pop below the launcher (#64, case E)
        stack.floor = len(stack)
        lifetime = runner.RunLifetime(
            stack,
            self.app.loop.call_soon_threadsafe,
            lambda error: self.finish_run(context, error, run_id),
        )
        self.script_runner.begin_run()
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
        self,
        context: runner.RunContext,
        error: BaseException | None,
        run_id: int | None = None,
    ) -> None:
        """Restore process state, report any error, and tidy up the Script tab.

        Runs once per run, on the loop (runner.RunLifetime). If a newer run has
        started meanwhile, only the process state is restored (#64, case G).
        """
        context.close()
        run_id = self.run_id if run_id is None else run_id
        if run_id != self.run_id:
            print(f"Run {run_id} ended after run {self.run_id} started; ignored")
            return
        self.script_runner.end_run()
        if error is None:
            self.end_script(run_id)
            return
        traceback.print_exception(error)
        self.script_activity.update("Failed", on=False)

        async def report() -> None:
            title = "Script Failure"
            if isinstance(error, (runner.NotRunnable, runner.UnsupportedGui)):
                message, title = str(error), "Can't Run"
            elif isinstance(error, SystemExit):
                message = f"Script exited with status {error.code}"
            else:
                message = f"Script failed with: {error!s}"
            await self.error(message, title)
            if run_id == self.run_id:
                self.end_script(run_id)

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

        # Packages with several entry points open like folders
        if getattr(selected_row, "package_up", False):
            self.package_dir = None
            self.reload_menu(widget)
            return
        if row_info.row_type(selected_row) == "package":
            self.package_dir = Path(cast(Any, selected_row).project_dir)
            self.reload_menu(widget)
            return

        # Folder rows (including "..") navigate instead of running anything
        if folder := getattr(selected_row, "folder", None):
            self.subfolder = pip.relative_folder(self.get_category_dir(), folder)
            self.reload_menu(widget)
            return

        if not row_info.runnable(row_info.row_type(selected_row)):
            return
        await self.run_row(selected_row)

    async def run_row(self, selected_row: Any) -> None:
        """Run a script or project row with the settings saved in its Setup."""
        settings, env = self.run_settings_for(selected_row)

        # 1. Read the parsed dependency requirements array
        required_packages = getattr(selected_row, "dependencies", [])

        target_user_packages = self.cache_path / "site_packages"
        if str(target_user_packages) not in sys.path:
            sys.path.insert(0, str(target_user_packages))

        # Switch to the Script view first, so installing dependencies shows
        # progress there instead of leaving the list looking frozen.
        title = getattr(selected_row, "title", "script")
        self.print_text.value = ""
        self.error_text.value = ""
        self.hide_errors()
        # Only a prototype's own icon is shown as a splash, never a default one
        if splash := getattr(selected_row, "splash", None):
            self.splash.image = splash
            self.splash.style.flex = 1
            self.script_output.style.flex = 0
        else:
            self.splash.image = None
            self.splash.style.flex = 0
            self.script_output.style.flex = 1
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
                    aliases={
                        **self.configured_aliases(),
                        **(getattr(selected_row, "aliases", None) or {}),
                    },
                )
            except Exception as e:  # noqa: BLE001
                # DependencyError, or e.g. an invalid requirement string
                traceback.print_exc()
                self.script_activity.update("Dependency install failed", on=False)
                await self.error(str(e), "Dependency Error")
                self.end_script()
                return

        # 3. Run it the way Python would: __main__, argv, its folder importable
        try:
            context = runner.RunContext(
                self.run_target(selected_row), argv=settings.args, env=env
            )
        except Exception as e:  # noqa: BLE001
            self.script_activity.update(on=False)
            await self.error(f"Failed to execute script:\n{e!s}", "Load Failure")
            self.end_script()
            return

        self.script_activity.update(f"Running {title}")
        self.app.loop.call_soon(lambda: self.start(context))

    def run_target(self, row: Any) -> runner.RunTarget:
        """What a runnable row runs: a file, or one of its project's entry points."""
        if entry := getattr(row, "entry", None):
            project_dir = Path(row.project_dir)
            folder_root = Path(getattr(row, "folder_root", project_dir))
            print(f"Launching {entry.name} ({entry.reference}) from {project_dir}")
            return runner.entry_target(
                entry.name, entry.reference, entry.kind, project_dir, folder_root
            )
        entry_point = Path(row.entry_point)
        folder_root = Path(getattr(row, "folder_root", entry_point.parent))
        print(f"Launching {row.title} from path: {entry_point}")
        if not entry_point.is_file():
            raise FileNotFoundError(f"Entry point not found: {entry_point}")
        return runner.target_for(entry_point, folder_root)

    # -- Swipe actions: Info and Setup (#59) -----------------------------------

    def row_path(self, row: Any) -> Path | None:
        """The file or folder a row stands for."""
        match row_info.row_type(row):
            case "category":
                return self.category_dirs()[row.category]
            case "folder":
                return Path(row.folder)
            case "script":
                return Path(row.entry_point)
            case "project" | "package" | "entry":
                return Path(row.project_dir)
            case _:
                return None

    def row_key(self, row: Any, *, entry: bool = True) -> str:
        """The key a row's settings are saved under: its path in its category.

        An entry point inside a package adds its name to the package's path,
        unless `entry` is False, which gives the package's own key.
        """
        path = self.row_path(row)
        assert self.category is not None and path is not None
        base = self.get_category_dir().resolve()
        try:
            relative = path.resolve().relative_to(base)
        except ValueError:
            relative = Path(path.name)
        name = None
        if entry and row_info.row_type(row) == "entry":
            name = row.entry.name
        return settings_key(self.category, relative, name)

    def up_destination(self, row: Any) -> str:
        """Where a ".." row leads, for messages."""
        if getattr(row, "categories", False) or self.category is None:
            return "the categories"
        if getattr(row, "package_up", False):
            return self.current_folder_name()
        parent = self.subfolder.parent
        if parent == Path():
            return self.category
        return f"{self.category}/{parent.as_posix()}"

    @property
    def settings(self) -> s.Settings:
        """The launcher's settings file."""
        return cast(Any, self.app).settings

    def setup_layer(self) -> Layer:
        """Setup's environment variables, inherited by every run."""
        return Layer("Setup", self.settings.get_environment())

    def inherited_layers(self, row: Any) -> list[Layer]:
        """The environment layers a row inherits: Setup, then its package's."""
        layers = [self.setup_layer()]
        if row_info.row_type(row) == "entry":
            package = self.settings.get_run_with(self.row_key(row, entry=False))
            layers.append(Layer(str(row.package_title), package.env))
        return layers

    def run_settings_for(self, row: Any) -> tuple[RunSettings, dict[str, str]]:
        """A runnable row's saved settings, and the environment it inherits.

        Setup's variables, then its package's, then its own: inner ones win.
        """
        own = self.settings.get_run_with(self.row_key(row))
        layers = [layer.env for layer in self.inherited_layers(row)]
        return own, merged_env([*layers, own.env])

    def handle_info(self, widget: toga.DetailedList, row: Any, **kwargs: Any) -> None:
        """Swipe left: Info."""
        asyncio.ensure_future(self.show_info(row))

    async def show_info(self, row: Any) -> None:
        """Show what's known about a row, or say why there's nothing."""
        kind = row_info.row_type(row)
        title = str(getattr(row, "title", ""))
        if kind == "up":
            await self.info(row_info.up_info_message(self.up_destination(row)), title)
            return
        if kind in ("category", "folder"):
            folder = self.row_path(row)
            assert folder is not None
            if readme := row_info.find_readme(folder):
                self.show_readme(title, readme)
                return
            message = row_info.no_readme_message(
                kind, title, pip.folder_summary(folder)
            )
            await self.info(message, title)
            return
        self.show_page(title, self.info_body(row))

    def info_body(self, row: Any) -> str:
        """The Info page for a script, project, package or entry point (#99)."""
        title = str(getattr(row, "title", ""))
        if row_info.row_type(row) == "script":
            return info_pages.script_info_html(Path(row.entry_point), title)
        entry = getattr(row, "entry", None)
        is_entry = row_info.row_type(row) == "entry"
        return info_pages.project_info_html(
            Path(row.project_dir),
            title,
            entry=entry,
            show_entries=not is_entry,
        )

    def show_readme(self, title: str, readme: Path) -> None:
        """Show a README on its own screen, rendered like the Help page."""
        try:
            text = readme.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            text = f"Couldn't read {readme.name}: {e}"
        self.show_page(title, readme_html(text, readme.name))

    def show_page(self, title: str, body: str) -> None:
        """Show an HTML fragment on its own screen with a Back button.

        Links to the web open in the system browser (see open_external).
        """
        view = toga.WebView(flex=1, on_navigation_starting=self.open_external)
        self.readme_page = html_page(body)
        view.content = self.readme_page
        self.readme_view = view
        self.push_screen(
            title,
            toga.Column(
                children=[
                    toga.Row(
                        children=[
                            toga.Button("‹ Back", on_press=lambda w: self.pop_screen())
                        ]
                    ),
                    view,
                ]
            ),
        )

    def open_external(self, widget: toga.WebView, url: str, **kwargs: Any) -> bool:
        """Open web links in the system browser, not inside the README view."""
        if url.startswith(("http://", "https://", "mailto:")):
            import webbrowser

            webbrowser.open(url)
            return False
        return True

    def handle_run_with(
        self, widget: toga.DetailedList, row: Any, **kwargs: Any
    ) -> None:
        """Swipe right: Setup."""
        asyncio.ensure_future(self.run_with(row))

    async def run_with(self, row: Any) -> None:
        """Open the Setup form, or say why a row has none."""
        kind = row_info.row_type(row)
        title = str(getattr(row, "title", ""))
        if not row_info.runnable(kind) and kind != "package":
            message = row_info.run_with_message(kind, title, self.up_destination(row))
            await self.info(message, title)
            return
        self.open_run_with(row)

    def open_run_with(self, row: Any) -> RunWithForm:
        """Open the Setup form for a runnable row or a package.

        A package with several entry points has no arguments of its own and
        can't run, so its form sets only the variables its entry points inherit.
        """
        key = self.row_key(row)
        saved = self.settings.get_run_with(key)
        runs = row_info.runnable(row_info.row_type(row))

        def save(settings: RunSettings) -> None:
            self.settings.set_run_with(key, settings, with_args=runs)

        form = RunWithForm(
            str(getattr(row, "title", "")),
            args=saved.args if runs else None,
            env=saved.env,
            inherited=self.inherited_layers(row),
            screens=self,
            on_save=save,
            ask=self.ask,
            tell=self.tell,
        )
        form.open()
        self.run_with_form = form
        return form

    def open_setup_environment(
        self, widget: toga.Widget | None = None, **kwargs: Any
    ) -> RunWithForm:
        """Setup's environment variables, inherited by every run."""
        form = RunWithForm(
            "Setup",
            args=None,
            env=self.settings.get_environment(),
            screens=self,
            on_save=lambda settings: self.settings.set_environment(settings.env),
            ask=self.ask,
            tell=self.tell,
            args_note="Every script and project inherits these variables. "
            "To override them, or set arguments, swipe right on a script and "
            "choose Setup.",
            screen_title="Environment",
        )
        form.open()
        self.run_with_form = form
        return form

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
            self.script_output.style.flex = 1

    def show_error_output(self, text: str) -> None:
        """Add a run's stderr text, showing the pane if it was hidden."""
        self.error_text.value += text
        self.error_pane.style.display = "pack"
        self.toggle_print(True)

    def hide_errors(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Hide the stderr pane until something is next written to it."""
        self.error_pane.style.display = "none"

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

    def configured_aliases(self) -> dict[str, pip.Alias]:
        """Package aliases from launcher.toml's [aliases] ({} if absent or bad)."""
        try:
            table = cast(Any, self.app).settings.get_table("aliases")
            return pip.parse_aliases(table)
        except (ValueError, OSError) as e:
            print(f"Ignoring [aliases] in launcher.toml: {e}")
            return {}

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
            aliases=self.configured_aliases(),
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

    @property
    def site_packages(self) -> Path:
        """Where prototypes' dependencies are installed."""
        return Path(self.cache_path) / "site_packages"

    async def confirm(self, text: str, title: str) -> bool:
        """Ask a yes/no question; True if the user said yes."""
        assert isinstance(self.app.main_window, toga.MainWindow)
        return bool(await self.app.main_window.dialog(toga.QuestionDialog(title, text)))

    def refresh_packages(self) -> None:
        """Count the user packages and their size."""
        count = len(pip.get_package_inventory(self.site_packages))
        if not count:
            self.packages_summary = "No user packages"
            return
        size = maintenance.human_size(maintenance.dir_size(self.site_packages))
        noun = "package" if count == 1 else "packages"
        self.packages_summary = f"{count} user {noun} ({size})"

    def with_client(self, check: Callable[..., Any], *args: Any) -> Any:
        """Run a network check with a short-lived HTTP client (off the loop)."""
        with httpx2.Client(timeout=15.0) as client:
            return check(client, *args)

    # -- Setup detail pages -------------------------------------------------

    SETUP_PAGES: ClassVar[dict[str, str]] = {
        "packages": "Packages",
        "health": "App health",
        "permissions": "Permissions",
    }

    def setup_page_html(self, page: str) -> str:
        """The HTML body of one Setup page, from the current state."""
        match page:
            case "packages":
                return setup_pages.packages_html(
                    self.packages_summary,
                    pip.get_package_inventory(self.site_packages),
                    self.checked_updates,
                    self.update_error,
                )
            case "health":
                return setup_pages.health_html(self.health, self.health_error)
            case _:
                return setup_pages.permissions_html(permissions.status(self.app))

    def render_setup_page(self) -> None:
        """Redraw the open Setup page, if there is one."""
        if self.setup_page is None:
            return
        self.setup_html = self.setup_page_html(self.setup_page)
        self.setup_view.content = html_page(self.setup_html)

    def setup_actions(self, page: str) -> list[toga.Widget]:
        """Native buttons for one Setup page's actions."""
        match page:
            case "packages":
                return [
                    toga.Button(
                        "Check for updates", on_press=self.handle_check_updates
                    ),
                    self.update_all_button,
                    toga.Button("Wipe user packages…", on_press=self.handle_wipe_cache),
                ]
            case "health":
                return [
                    toga.Button("Check app health", on_press=self.handle_check_health)
                ]
            case _:
                return [
                    toga.Button("Open Settings", on_press=self.handle_open_settings)
                ]

    def open_setup_page(self, page: str) -> None:
        """Show a Setup page over the launcher, with a Back button.

        It's pushed onto the window's content stack like any other view, so Back
        pops it and restores the tabs as they were.
        """
        if page == "packages":
            self.refresh_packages()
        actions = self.setup_actions(page)
        # These widgets are reused, so take them out of the last page first
        for widget in (self.setup_view, self.setup_activity, *actions):
            if widget.parent is not None:
                widget.parent.remove(widget)
        self.setup_activity.update(on=False)
        content = toga.Column(
            children=[
                toga.Row(
                    children=[toga.Button("‹ Back", on_press=self.close_setup_page)]
                ),
                self.setup_view,
                toga.Column(margin=(4, 8), children=actions),
                self.setup_activity,
            ]
        )
        self.push_screen(self.SETUP_PAGES[page], content)
        self.setup_page = page
        self.render_setup_page()

    def close_setup_page(
        self, widget: toga.Widget | None = None, **kwargs: Any
    ) -> None:
        """Back: pop the Setup page and return to the tabs."""
        self.pop_screen()
        self.setup_page = None

    def push_screen(self, title: str, content: toga.Widget) -> None:
        """Show `content` over the launcher; :meth:`pop_screen` goes back.

        Screens go on the window's content stack like any other view. The
        floor stops a double-tapped Back from popping past this screen.
        """
        mw = self.app.main_window
        assert isinstance(mw, toga.MainWindow)
        stack = self.content_stack()
        self.screen_bases.append(len(stack))
        stack.floor = len(stack)
        stack.append((mw.title, mw.content))
        mw.title = title
        mw.content = content

    def pop_screen(self) -> None:
        """Go back to the screen under the last :meth:`push_screen`.

        A pop below the floor is ignored by the stack. After popping a screen
        that was pushed over another of ours (an editor over the Setup
        form), the floor drops back so that one can be popped too.
        """
        mw = self.app.main_window
        assert isinstance(mw, toga.MainWindow)
        stack = self.content_stack()
        popping = len(stack) > stack.floor
        mw.title, mw.content = stack.pop()
        if popping and self.screen_bases:
            self.screen_bases.pop()
            if self.screen_bases:
                stack.floor = self.screen_bases[-1]

    def setup_menu_button(self, page: str) -> toga.Button:
        """A Setup menu entry that opens one of the detail pages."""
        return toga.Button(
            f"{self.SETUP_PAGES[page]} ›", on_press=lambda w: self.open_setup_page(page)
        )

    # -- Setup actions --------------------------------------------------------

    def handle_open_settings(self, widget: toga.Widget, **kwargs: Any) -> None:
        """Open this app's page in the iOS Settings app."""
        if not permissions.open_app_settings():
            self.setup_activity.update("Settings can only be opened on iOS", on=False)

    async def handle_wipe_cache(self, widget: toga.Widget, **kwargs: Any) -> None:
        """Delete user-installed packages, after confirmation."""
        if not await self.confirm(
            "Delete all user-installed packages? Prototypes reinstall their "
            "dependencies on their next run, which needs the network.",
            "Wipe user packages",
        ):
            return
        await asyncio.to_thread(maintenance.wipe, self.site_packages)
        importlib.invalidate_caches()
        self.pending_updates = []
        self.checked_updates = None
        self.update_error = None
        self.update_all_button.enabled = False
        self.refresh_packages()
        self.render_setup_page()
        self.setup_activity.update("User packages deleted", on=False)

    async def handle_check_updates(self, widget: toga.Widget, **kwargs: Any) -> None:
        """Ask PyPI whether user packages have newer versions."""
        self.setup_activity.update("Checking PyPI for updates")
        inventory = pip.get_package_inventory(self.site_packages)
        try:
            updates = await asyncio.to_thread(
                self.with_client, maintenance.find_updates, inventory
            )
        except maintenance.MaintenanceError as e:
            self.pending_updates = []
            self.update_error = str(e)
            self.update_all_button.enabled = False
            self.render_setup_page()
            self.setup_activity.update(str(e), on=False)
            return
        self.pending_updates = updates
        self.checked_updates = updates
        self.update_error = None
        self.update_all_button.enabled = bool(updates)
        self.render_setup_page()
        found = f"{len(updates)} update(s) available" if updates else "Up to date"
        self.setup_activity.update(found, on=False)

    async def handle_update_all(self, widget: toga.Widget, **kwargs: Any) -> None:
        """Install the versions found by the last update check."""
        if not self.pending_updates:
            return
        requirements = maintenance.upgrade_requirements(self.pending_updates)
        try:
            await pip.resolve_and_install_async(
                requirements,
                self.site_packages,
                on_progress=self.setup_activity.update,
            )
        except Exception as e:  # noqa: BLE001
            self.setup_activity.update("Update failed", on=False)
            await self.error(str(e), "Update failed")
            return
        self.pending_updates = []
        self.checked_updates = []
        self.update_all_button.enabled = False
        self.refresh_packages()
        self.render_setup_page()
        self.setup_activity.update("Packages updated", on=False)

    async def handle_check_health(self, widget: toga.Widget, **kwargs: Any) -> None:
        """Compare Python and bundled packages with python.org and PyPI."""
        self.setup_activity.update("Checking python.org and PyPI")
        bundled = pip.get_bundled_inventory(self.site_packages)

        def check(client: httpx2.Client) -> maintenance.Health:
            python = maintenance.check_python(client, platform.python_version())
            updates = maintenance.find_updates(
                client, bundled, critical=maintenance.APP_CRITICAL
            )
            return maintenance.Health(python, updates)

        try:
            health = await asyncio.to_thread(self.with_client, check)
        except maintenance.MaintenanceError as e:
            self.health_error = str(e)
            self.render_setup_page()
            self.setup_activity.update(on=False)
            return
        self.health = health
        self.health_error = None
        self.render_setup_page()
        self.setup_activity.update(on=False)

    def setup_sections(self) -> list[toga.Widget]:
        """The Setup tab: a short menu; details open on their own pages."""

        def heading(text: str) -> toga.Label:
            return toga.Label(text, font_weight="bold", margin=(12, 0, 4, 0))

        exit_visible = len(getattr(self.app.main_window, "content_stack", [])) > 0
        return [
            heading("Projects"),
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
            toga.Button("Environment ›", on_press=self.open_setup_environment),
            heading("Maintenance"),
            *(self.setup_menu_button(page) for page in self.SETUP_PAGES),
            heading("App"),
            toga.Button("Backup", on_press=self.handle_backup_press),
            toga.Button(
                "Exit",
                visibility="visible" if exit_visible else "hidden",
                on_press=self.do_on_done_callback,
            ),
        ]

    def choose_container(self, *args: Any, **kwargs: Any) -> toga.Widget:
        assert isinstance(self.app.main_window, toga.MainWindow)
        if is_ipad_from_window(self.app.main_window):
            return NotAnOptionContainer(*args, **kwargs)
        else:
            return toga.OptionContainer(*args, **kwargs)

    def do_on_done_callback(self, widget: toga.Widget, **kwargs: Any) -> None:
        # Leaving the launcher on purpose: lift the guard against extra pops
        self.content_stack().floor = 0
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
                            self.script_output,
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
                            toga.ScrollContainer(
                                horizontal=False,
                                flex=1,
                                content=toga.Column(
                                    margin=(0, 8),
                                    children=self.setup_sections(),
                                ),
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
