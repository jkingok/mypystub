"""The launcher's shared state and services: what every part of it builds on."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import toga
from toga.style import Pack

from . import hooks as h
from . import piplike as pip
from . import (
    prompts,
    runner,
    scan,
)
from . import settings as s
from .errors import guarded
from .pages import html_page
from .ui_widgets import LabelledActivity
from .widgets import OrientationBox

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
    "zipapp": "zipapp.png",
}

# Entry points inside a package, by kind. Placeholders until the icons are
# added: a missing file shows no icon (see bundled_icon).
ENTRY_ICONS = {
    "cli": "terminal.png",
    "gui": "window.png",
    "other": "plug.png",
}


class PrototypeBase:
    """Everything the feature mixins share: widgets, dialogs, folders, screens.

    Feature mixins (running, swipes, paste, Setup) build on this and never
    reach into the class that combines them.
    """

    def __init__(self, host_app: toga.App, on_done: Callable[[Any], None]) -> None:
        self.app = host_app
        self.on_done_callback = on_done  # This is your ticket back to safety
        self.title = "Launcher"  # host_app.formal_name
        # The launcher keeps its own state (settings, widgets) on itself and
        # never on the shared app object or its widget registry: prototypes run
        # in this process, and some set app.settings or reuse widget ids.
        self.launcher_settings = s.Settings(host_app.paths)
        self.cache_path = self.app.paths.cache
        self.data_path = getattr(self.app, "user_documents_dir", self.app.paths.data)
        print(f"Prototype initialized with data_path: {self.data_path}")
        self.this_path = Path(__file__).resolve().parent
        self.icon_path = self.this_path / "resources" / "icons"
        self.template_path = self.this_path / "resources" / "templates"
        self.prototype_dir = self.data_path
        self.ask_text_fields: list[toga.TextInput] = []  # the fallback prompt's
        # The tabs, once get_content has built them
        self.tabs: Any = None
        self.script_box = toga.Column()  # the Script tab; input boxes go on top
        self.keyboard_box = toga.Box(style=Pack(flex=0))  # pads for the keyboard
        self.new_project_name: toga.TextInput | None = None
        self.input_prompt = toga.Label("Input")
        self.input_text = toga.TextInput(
            style=Pack(flex=1),
            on_gain_focus=self.gain_focus,
            on_lose_focus=self.lose_focus,
        )
        self.input_box = toga.Column(
            children=[self.input_prompt, self.input_text], text_align="center"
        )
        # getpass() asks here instead, so the password isn't shown (#121)
        self.password_prompt = toga.Label("Password")
        self.password_text = toga.PasswordInput(
            style=Pack(flex=1),
            on_gain_focus=self.gain_focus,
            on_lose_focus=self.lose_focus,
        )
        self.password_box = toga.Column(
            children=[self.password_prompt, self.password_text], text_align="center"
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
            password_label=self.password_prompt,
            password_field=self.password_text,
            toggle_password=self.toggle_password,
        )
        self.script_scroll = toga.ScrollContainer(
            horizontal=False, content=self.print_text, style=Pack(flex=1)
        )
        self.script_output = OrientationBox(self.script_scroll, self.error_pane)
        self.script_activity = LabelledActivity()
        self.splash = toga.ImageView(style=Pack(flex=0))
        # Category being browsed (None: the list of categories), and the folder
        # within it, relative to the category's root
        self.category: str | None = None
        self.subfolder = Path()
        # A package with several entry points that's open, listing them
        self.package_dir: Path | None = None
        # The page each web view shows now (by id), so it isn't loaded twice
        self.loaded_pages: dict[int, str] = {}
        # Content-stack depths under each screen pushed by push_screen()
        self.screen_bases: list[int] = []
        # Toga's swipe actions are the same for every row (#59): swipe left
        # for Info, swipe right for Setup. The mixins that own them set the
        # handlers, as on_select belongs to running and the swipes to Info/Setup.
        self.script_list = toga.DetailedList(
            on_refresh=self.reload_menu,
            primary_action="Info",
            secondary_action="Setup",
            style=Pack(flex=1),
        )

    async def todo(self, name: str) -> None:
        assert isinstance(self.app.main_window, toga.MainWindow)
        await self.app.main_window.dialog(toga.InfoDialog("TODO", name))

    async def ask_fields(
        self,
        title: str,
        message: str,
        fields: list[prompts.Field],
        ok: str = "Done",
    ) -> list[str] | None:
        """Ask for one or more lines of text; the texts, or None if cancelled.

        On iOS this is a native alert over the current screen. Elsewhere Toga
        has no text dialog, so a screen of its own is pushed instead.
        """
        if prompts.NATIVE:
            return await prompts.ask_fields(
                lambda *a: prompts.present_alert(self.app, *a),  # pyright: ignore
                title,
                message,
                fields,
                ok,
            )
        return await self.ask_fields_screen(title, message, fields, ok)

    async def ask_fields_screen(
        self,
        title: str,
        message: str,
        fields: list[prompts.Field],
        ok: str = "Done",
    ) -> list[str] | None:
        """The fallback for :meth:`ask_fields`: a pushed screen of text inputs."""
        answer: asyncio.Future[list[str] | None] = (
            asyncio.get_running_loop().create_future()
        )
        inputs = [
            toga.TextInput(value=f.value, placeholder=f.label, flex=1) for f in fields
        ]
        self.ask_text_fields = inputs

        def finish(value: list[str] | None) -> None:
            if not answer.done():
                self.pop_screen()
                answer.set_result(value)

        rows: list[toga.Widget] = [toga.Label(message)] if message else []
        for field, widget in zip(fields, inputs):
            rows.append(toga.Label(field.label))
            rows.append(toga.Box(children=[widget]))
        rows.append(
            toga.Box(
                style=Pack(margin=(8, 0)),
                children=[
                    toga.Button("Cancel", on_press=lambda w: finish(None)),
                    toga.Box(style=Pack(flex=1)),
                    toga.Button(
                        ok, on_press=lambda w: finish([str(i.value) for i in inputs])
                    ),
                ],
            )
        )
        self.push_screen(
            title,
            toga.Box(style=Pack(direction="column", margin=8), children=rows),
        )
        return await answer

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

    async def report_error(self, error: Exception, where: str) -> None:
        """Tell the user about an error that a handler raised (see errors.guarded)."""
        await self.error(f"{type(error).__name__}: {error}\n\n(in {where})", "Error")

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

            # A property, as toga_iOS's other colours are. Calling it as a method
            # first would stop a later declaration working, and scripts share this
            # class: toga-console declares it and draws nothing if that fails.
            UIColor.declare_class_property("labelColor")
            native = image._impl.native
            image._impl.native = native.imageWithTintColor(
                UIColor.labelColor,
                renderingMode=1,  # UIImageRenderingModeAlwaysOriginal
            )
        return image

    @guarded
    def reload_menu(
        self, widget: toga.DetailedList | toga.Selection, **kwargs: Any
    ) -> None:
        # 0. At the top, the list is the categories themselves
        if self.category is None:
            self.script_list.data = [
                {
                    "title": name,
                    "subtitle": scan.folder_summary_compact(path),
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
        self.prototypes_data = scan.scan_all_prototypes(self.get_current_dir())

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
        package = (
            scan.scan_zipapp(package_dir)
            if package_dir.is_file()
            else scan.scan_project(package_dir)
        )
        rows: list[dict[str, Any]] = [
            {
                "title": "..",
                "subtitle": f"Back to {self.current_folder_name()}",
                "icon": self.bundled_icon("arrow-small-left.png"),
                "package_up": True,
            }
        ]
        for row in scan.entry_rows(package) if package["kind"] == "package" else []:
            row.pop("icon_path")
            row["icon"] = self.bundled_icon(ENTRY_ICONS[row["entry"].kind])
            row["splash"] = None
            rows.append(row)
        return rows

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

    def load_page(self, view: toga.WebView, body: str) -> None:
        """Show an HTML fragment in a web view, unless it already shows that page.

        Building the tabs shows Help, selecting its tab asks again, and Setup
        pages are redrawn after each change, so the same page was being loaded
        two or three times; each load blanks and redraws the view.
        """
        page = html_page(body)
        if self.loaded_pages.get(id(view)) == page:
            return
        self.loaded_pages[id(view)] = page
        view.content = page

    def configured_aliases(self) -> dict[str, pip.Alias]:
        """Package aliases from launcher.toml's [aliases] ({} if absent or bad)."""
        try:
            table = self.settings.get_table("aliases")
            return pip.parse_aliases(table)
        except (ValueError, OSError) as e:
            print(f"Ignoring [aliases] in launcher.toml: {e}")
            return {}

    @property
    def settings(self) -> s.Settings:
        """The launcher's settings file."""
        return self.launcher_settings

    @guarded
    def open_external(self, widget: toga.WebView, url: str, **kwargs: Any) -> bool:
        """Open web links in the system browser, not inside a web view (README, Info, About)."""
        if url.startswith(("http://", "https://", "mailto:")):
            import webbrowser

            webbrowser.open(url)
            return False
        return True

    def pad_keyboard(self, on: bool) -> None:
        # keyboard_box.style.visibility = "visible" if on else "hidden"
        self.keyboard_box.style.flex = 1 if on else 0

    @guarded
    def gain_focus(self, widget: toga.TextInput, **kwargs: Any) -> None:
        self.pad_keyboard(True)

    @guarded
    def lose_focus(self, widget: toga.TextInput, **kwargs: Any) -> None:
        self.pad_keyboard(False)

    def toggle_input(self, on: bool) -> None:
        self.toggle_box(self.input_box, on)

    def toggle_password(self, on: bool) -> None:
        """Show or hide the password field that getpass() asks with."""
        self.toggle_box(self.password_box, on)

    def toggle_box(self, box: toga.Box, on: bool) -> None:
        """Show `box` at the top of the Script tab, or take it away."""
        script_box = self.script_box
        if on:
            if box.parent is None:
                script_box.insert(0, box)
        elif box.parent is not None:
            script_box.remove(box)
        self.pad_keyboard(on)

    def toggle_print(self, on: bool) -> None:
        if on:
            self.splash.style.flex = 0
            self.script_output.style.flex = 1

    @guarded
    def show_error_output(self, text: str) -> None:
        """Add a run's stderr text, showing the pane if it was hidden."""
        self.error_text.value += text
        self.error_pane.style.display = "pack"
        self.toggle_print(True)

    @guarded
    def hide_errors(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Hide the stderr pane until something is next written to it."""
        self.error_pane.style.display = "none"

    @guarded
    def do_on_done_callback(self, widget: toga.Widget, **kwargs: Any) -> None:
        # Leaving the launcher on purpose: lift the guard against extra pops
        self.content_stack().floor = 0
        self.on_done_callback(widget)
