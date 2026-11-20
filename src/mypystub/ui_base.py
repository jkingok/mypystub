"""The launcher's shared state and services: what every part of it builds on."""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from typing import Any

import toga
from toga.style import Pack

from . import (
    examples_copy,
    logfile,
    native,
    prompts,
    resume,
    runner,
    scan,
    ui_console,
    web_meta,
)
from . import hooks as h
from . import piplike as pip
from . import settings as s
from .errors import guarded
from .pages import html_page
from .run_settings import SYSTEM, Layer, env_name_problem, env_value_problem
from .safe_area import SafeArea, SafeColumn
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

# Platforms whose DetailedList takes a toga.Image as a row icon (see list_icon)
IMAGE_ICON_PLATFORMS = ("ios", "android", "darwin")

KIND_ICONS = {
    "folder": "folder.png",
    "project": "box.png",
    "package": "boxes.png",  # a project with several entry points
    "script": "file-code.png",
    "zipapp": "zipapp.png",
    "web": "web.png",  # added later; a missing icon file is skipped
}

# Entry points inside a package, by kind. Placeholders until the icons are
# added: a missing file shows no icon (see bundled_icon).
ENTRY_ICONS = {
    "cli": "terminal.png",
    "gui": "window.png",
    "other": "plug.png",
}


PRESERVE_LOGS_SETTING = "preserve_logs"  # launcher.toml: keep the log
RESUME_SETTING = "resume"  # launcher.toml: false starts fresh every time


# Seconds a closed question waits for the next one before its keyboard goes
KEYBOARD_GRACE = 0.3


class PrototypeBase:
    """Everything the feature mixins share: widgets, dialogs, folders, screens.

    Feature mixins (running, swipes, paste, Setup) build on this and never
    reach into the class that combines them.
    """

    def __init__(self, host_app: toga.App, on_done: Callable[[Any], None]) -> None:
        self.app = host_app
        self.on_done_callback = on_done  # This is your ticket back to safety
        self.title = "Launcher"  # host_app.formal_name
        # The last script run, which the window is titled with on the Script tab
        self.run_title: str | None = None
        # The launcher keeps its own state (settings, widgets) on itself and
        # never on the shared app object or its widget registry: prototypes run
        # in this process, and some set app.settings or reuse widget ids.
        self.launcher_settings = s.Settings(host_app.paths)
        self.cache_path = self.app.paths.cache
        self.fetching_icons: set[str] = set()  # online web app icons being fetched
        self.data_path = getattr(self.app, "user_documents_dir", self.app.paths.data)
        print(f"Prototype initialized with data_path: {self.data_path}")
        self.this_path = Path(__file__).resolve().parent
        self.examples_path = self.examples_location()
        self.icon_path = self.this_path / "resources" / "icons"
        self.template_path = self.this_path / "resources" / "templates"
        self.prototype_dir = self.data_path
        # What iOS (or the OS) set before this app ran: the outermost layer of the
        # environment Setup shows. Taken now, before any run changes os.environ.
        # Whether Setup screens list inherited variables; they all follow this
        # Whether forms list inherited variables; None until the user chooses,
        # so each form picks (shown when it has none of its own, #304)
        self.show_inherited_env: bool | None = None
        self.system_env: dict[str, str] = {
            name: value
            for name, value in os.environ.items()
            if env_name_problem(name) is None and env_value_problem(value) is None
        }
        self.ask_text_fields: list[toga.TextInput] = []  # the fallback prompt's
        # The tabs, once get_content has built them
        self.tabs: Any = None
        # A script that is running: (settings key, title). If the app is ended
        # while it is set, the next launch offers to run it again (#188).
        self.resume_running: tuple[str, str] | None = None
        # False until the saved state has been read: until then a snapshot of the
        # freshly built launcher would overwrite what is about to be restored
        self.resume_ready = False
        self._resume_written: resume.Resume | None = None
        # The Script tab. While input() or getpass() asks, its box takes the
        # activity row's place at the bottom (see toggle_box).
        self.script_box = toga.Column()
        self.input_prompt = toga.Label("Input")
        self.input_text = toga.TextInput(style=Pack(flex=1))
        self.input_box = toga.Column(
            children=[self.input_prompt, self.input_text], text_align="center"
        )
        # getpass() asks here instead, so the password isn't shown (#121)
        self.password_prompt = toga.Label("Password")
        self.password_text = toga.PasswordInput(style=Pack(flex=1))
        self.password_box = toga.Column(
            children=[self.password_prompt, self.password_text], text_align="center"
        )
        # A MultilineTextInput scrolls itself. Inside a ScrollContainer it is laid
        # out at its own small minimum, and isn't laid out again when the space
        # changes (rotation, the error pane hiding), so it fills the box itself.
        self.print_text = toga.MultilineTextInput(readonly=True, flex=1)
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
        self.script_output = OrientationBox(self.print_text, self.error_pane, flex=1)
        # Setup's Experimental Console, made when a run first wants it
        self.console_widget: Any = None
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
        # Content-stack depths under each screen pushed by push_screen(), and
        # what the system Back button does on each (its own Back or Cancel)
        self.screen_bases: list[int] = []
        self.back_actions: list[Callable[[], Any]] = []
        # The tabs in the order they were shown, for Back (see BackMixin)
        self.tab_history: list[str] = []
        # Toga's swipe actions are the same for every row (#59): swipe left
        # for Info, swipe right for Setup. The mixins that own them set the
        # handlers, as on_select belongs to running and the swipes to Info/Setup.
        if sys.platform == "android":
            from . import android_list

            android_list.install()  # a long press must not also run the row
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
            on_back=lambda: finish(None),
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

    @property
    def experimental_console(self) -> bool:
        """Whether runs use toga-console in the Script tab (Setup; off)."""
        return self.settings.get_flag(ui_console.SETTING, False)

    def set_experimental_console(self, on: bool) -> None:
        """Turn the Experimental Console on or off, from the next run."""
        self.settings.set_flag(ui_console.SETTING, on)

    def choose_output(self) -> None:
        """At the start of a run: the console or the usual output, emptied.

        The choice is made per run, so the Setup switch takes effect from the
        next one. If toga-console can't be loaded, the usual output is used.
        """
        wanted = None
        if self.experimental_console:
            if self.console_widget is None:
                self.console_widget = ui_console.make_console()
            wanted = self.console_widget
        shown = wanted if wanted is not None else self.print_text
        current = self.script_output.children[0]
        if current is not shown:
            self.script_output.replace(current, shown)
            shown.style.flex = 1
        self.script_runner.console = wanted
        if wanted is not None:
            wanted.clear()
            wanted.readonly = True
        self.print_text.value = ""

    @property
    def preserve_logs(self) -> bool:
        """Whether the log is kept between launches (Setup's Preserve Logs)."""
        return self.settings.get_flag(PRESERVE_LOGS_SETTING, False)

    def set_preserve_logs(self, preserve: bool) -> None:
        """Turn Preserve Logs on or off. Off only matters at the next start."""
        self.settings.set_flag(PRESERVE_LOGS_SETTING, preserve)

    @property
    def native_mode(self) -> bool:
        """Desktop runs use pip and a subprocess (#280): on by default."""
        return native.available() and self.settings.get_flag(native.SETTING, True)

    def set_native_mode(self, on: bool) -> None:
        """Save Setup's Native mode switch."""
        self.settings.set_flag(native.SETTING, on)

    def apply_log_policy(self) -> None:
        """At launch, empty the log unless Preserve Logs is on."""
        redirector = logfile.current()
        if redirector is not None and not self.preserve_logs:
            redirector.truncate()

    async def show_info_for(self, path: Path) -> None:
        """Show the Info page of the row for `path`, if the list has one.

        A hook: the base does nothing; SwipeMixin, which owns Info, shows it.
        """

    def remember(self) -> None:
        """Save where the user is (see ResumeMixin); does nothing in the base."""

    @property
    def resume_path(self) -> Path:
        """Where the resume state is kept (#188): beside launcher.toml.

        Not in the data folder, which on iOS is Documents, shown in Files.
        """
        return resume.state_path(Path(self.app.paths.config))

    @property
    def resume_enabled(self) -> bool:
        """Whether the launcher resumes (the Setup switch; on by default)."""
        return self.settings.get_flag(RESUME_SETTING, True)

    def set_resume_enabled(self, enabled: bool) -> None:
        """Turn resuming on or off; off also forgets what was saved."""
        self.settings.set_flag(RESUME_SETTING, enabled)
        self._resume_written = None
        if enabled:
            self.remember()
        else:
            resume.clear(self.resume_path)

    def close_keyboard(self, widget: toga.Widget, **kwargs: Any) -> None:
        """Put away the keyboard `widget` opened (also on Return or Done).

        iOS resigns its first responder; Android hides its input method and
        drops the focus (see android_keyboard). Elsewhere there is nothing to do.
        """
        if sys.platform == "ios":
            widget._impl.native.resignFirstResponder()
        elif sys.platform == "android":
            from . import android_keyboard

            android_keyboard.hide(widget._impl.native)

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

    def examples_location(self) -> Path:
        """The Examples folder: a private copy on Android, else the bundled one."""
        source = resources.files("mypystub") / "resources" / "examples"
        try:
            return examples_copy.examples_location(
                source, Path(self.cache_path), sys.platform
            )
        except OSError as e:
            print(f"Couldn't copy the examples; using the bundled ones: {e}")
            return Path(str(source))

    def category_dirs(self) -> dict[str, Path]:
        """The top-level categories: built-in examples and the user's Documents."""
        return {
            "Examples": self.examples_path,
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

    def bundled_icon(self, filename: str) -> toga.Icon | toga.Image | None:
        """Load an icon from resources/icons, or None until the file is added."""
        path = self.icon_path / filename
        if not path.exists():
            return None
        return self.list_icon(path, tint=True)

    @staticmethod
    def list_icon(path: Path, tint: bool = False) -> toga.Icon | toga.Image:
        """An image for a DetailedList row, in the form this platform accepts.

        Toga documents a row's icon as a ``toga.Icon``. The iOS, Android and
        macOS (Cocoa) backends also take a ``toga.Image``, which is what lets the
        launcher tint its line-art icons on iOS (below). The Windows backend
        doesn't: it needs the icon's ``path``, and a Toga Image has none. So
        everywhere else the file is loaded as an Icon.
        """
        if sys.platform not in IMAGE_ICON_PLATFORMS:
            return toga.Icon(path)
        image = toga.Image(path)
        if tint and sys.platform == "ios":
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

    def web_icon_cache(self) -> Path:
        """Where web apps' icons are kept, converted for the list (#150)."""
        return Path(self.cache_path) / "web_icons"

    def fetch_web_icons(self, rows: Any) -> None:
        """Fetch the online icons of web app rows, then redraw the list.

        Done once per icon, off the UI thread; a failure is remembered so a
        dead link isn't tried on every redraw (see web_meta.fetch_remote).
        """
        urls = [
            url
            for row in rows
            for url in row.get("icon_pending", [])
            if url not in self.fetching_icons
        ]
        if not urls:
            return
        self.fetching_icons.update(urls)
        cache = self.web_icon_cache()

        async def fetch() -> None:
            got = False
            for url in urls:
                got |= await asyncio.to_thread(web_meta.fetch_remote, url, cache)
            self.fetching_icons.difference_update(urls)
            if got:
                self.reload_menu(self.script_list)

        asyncio.ensure_future(fetch())

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
        self.prototypes_data = scan.scan_all_prototypes(
            self.get_current_dir(), self.web_icon_cache()
        )
        self.fetch_web_icons(self.prototypes_data)

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
            own_icon = row_icon = None
            if proto["icon_path"] and proto["icon_path"].exists():
                # The splash is an ImageView, which wants an Image; the row an
                # icon in the form this platform's list accepts
                own_icon = toga.Image(proto["icon_path"])
                row_icon = self.list_icon(proto["icon_path"])
            icon_file = KIND_ICONS.get(proto.get("kind", ""))
            if row_icon is None and icon_file:
                row_icon = self.bundled_icon(icon_file)

            # Toga ignores the custom keys (entry_point, folder, ...) for rendering,
            # but holds onto them for callbacks!
            row = {
                k: v for k, v in proto.items() if k not in ("icon_path", "icon_pending")
            }
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

    def push_screen(
        self,
        title: str,
        content: toga.Widget,
        on_back: Callable[[], Any] | None = None,
    ) -> None:
        """Show `content` over the launcher; :meth:`pop_screen` goes back.

        Screens go on the window's content stack like any other view. The
        floor stops a double-tapped Back from popping past this screen.
        `on_back` is what the system Back button does here: the screen's own
        Back or Cancel, if it does more than pop (see BackMixin). The screen
        is kept clear of the home indicator, notch and keyboard (SafeArea).
        """
        if not isinstance(content, SafeArea):
            if content.style.flex == 0:
                content.style.flex = 1  # fill the screen, as window content does
            content = SafeColumn(children=[content])
        self.back_actions.append(on_back or self.pop_screen)
        mw = self.app.main_window
        assert isinstance(mw, toga.MainWindow)
        stack = self.content_stack()
        self.screen_bases.append(len(stack))
        stack.floor = len(stack)
        stack.append((mw.title, mw.content))
        mw.title = title
        mw.content = content

    def apply_window_title(self) -> None:
        """Title the window for the tab showing (#235).

        "Launcher" on every tab but Script, which shows the last script run.
        Only while the tabs are on screen: a pushed screen or a prototype's
        takeover titles the window itself, and this puts it back afterwards
        (a prototype may have changed it).
        """
        mw = self.app.main_window
        if not isinstance(mw, toga.MainWindow) or self.tabs is None:
            return
        if mw.content is not self.tabs:
            return
        current: Any = self.tabs.current_tab
        on_script = current is not None and str(current.text) == "Script"
        mw.title = self.run_title if on_script and self.run_title else self.title

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
            if self.back_actions:
                self.back_actions.pop()
            if self.screen_bases:
                stack.floor = self.screen_bases[-1]
        self.apply_window_title()

    def add_button_icon(
        self, button: toga.Button, icon_file: str, size: int = 20
    ) -> None:
        """On iOS, draw a bundled icon beside a button's text, tinted like it.

        Toga won't give a button both text and an icon, so the image is set
        natively (the same call toga-iOS makes), as a template so it follows
        the button's colour and dark mode. Nothing happens if the icon file
        hasn't been added, or off iOS.
        """
        path = self.icon_path / icon_file
        if sys.platform != "ios" or not path.exists():
            return
        from toga_iOS.libs import UIControlStateNormal

        image = (
            toga.Icon(path)
            ._impl._as_size(size)
            .imageWithRenderingMode(2)  # UIImageRenderingModeAlwaysTemplate
        )
        button._impl.native.setImage(image, forState=UIControlStateNormal)
        # Toga measured the button from its text alone; measure it again now
        # that the image is there, or the label can be squeezed ("P...te")
        button.refresh()

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

    @guarded
    def set_show_inherited_env(self, shown: bool) -> None:
        """Remember the choice to list inherited variables on every Setup screen."""
        self.show_inherited_env = shown

    @property
    def inherited_icon(self) -> Any:
        """The icon marking inherited variables in Setup's lists, if bundled (#304)."""
        path = self.icon_path / "inherited.png"
        return self.list_icon(path, tint=True) if path.exists() else None

    def system_layer(self) -> Layer:
        """The environment the app started with, which iOS (or the OS) set."""
        return Layer(SYSTEM, self.system_env)

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

    def toggle_input(self, on: bool) -> None:
        self.toggle_box(self.input_box, on)

    def toggle_password(self, on: bool) -> None:
        """Show or hide the password field that getpass() asks with."""
        self.toggle_box(self.password_box, on)

    def toggle_box(self, box: toga.Box, on: bool) -> None:
        """Swap `box` (input's or getpass's) in for the activity row, or back.

        The question goes at the bottom of the Script tab, under the output it
        follows, as at a terminal. The keyboard doesn't hide it: on iOS and
        Android the tab's SafeArea keeps the tab above the keyboard. While it
        asks, the activity row ("Running ...") gives it its place, so the output
        keeps the room that is left.
        """
        script_box = self.script_box
        activity = self.script_activity
        if on:
            if box.parent is not None:
                return
            if activity.parent is not None:  # it only ever sits in the Script tab
                script_box.replace(activity, box)
            else:  # already asking with the other box
                script_box.add(box)
        elif box.parent is not None:
            field = self.password_text if box is self.password_box else self.input_text
            self.close_keyboard_soon(field)
            asking = [b for b in (self.input_box, self.password_box) if b.parent]
            if len(asking) == 1 and activity.parent is None:
                script_box.replace(box, activity)
            else:
                script_box.remove(box)

    def close_keyboard_soon(self, field: toga.Widget) -> None:
        """Put the keyboard away if no question follows the one just answered.

        Android leaves its keyboard up when the focused field is taken away,
        and moves the focus to the tab bar, so it is closed here. A script that
        asks again straight away (a REPL's next prompt) keeps the keyboard up,
        so the check waits a moment for the next question first.
        """

        def unless_asking() -> None:
            if self.input_box.parent is None and self.password_box.parent is None:
                self.close_keyboard(field)

        loop = getattr(self.app, "loop", None)
        if loop is None:
            unless_asking()
        else:
            loop.call_later(KEYBOARD_GRACE, unless_asking)

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
