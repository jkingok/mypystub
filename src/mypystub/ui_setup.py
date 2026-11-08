"""The Setup tab: its menu, detail pages and actions."""

from __future__ import annotations

import asyncio
import importlib
import platform
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

import httpx2
import toga

from . import (
    about,
    files_app,
    maintenance,
    permissions,
    setup_pages,
)
from . import piplike as pip
from .errors import guarded
from .pages import without_title
from .run_settings import quick_start_name
from .run_with import RunWithForm
from .ui_base import PrototypeBase
from .ui_helpers import (
    create_nested_app_backup,
    open_share_sheet,
)
from .ui_widgets import LabelledActivity


class SetupMixin(PrototypeBase):
    """The Setup tab and the pages it opens."""

    def __init__(self, host_app: toga.App, on_done: Callable[[Any], None]) -> None:
        super().__init__(host_app, on_done)
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

    def new_project_field(self) -> toga.TextInput:
        """The New Project name field, which the launcher keeps hold of."""
        self.new_project_name = toga.TextInput(flex=1, on_confirm=self.close_keyboard)
        return self.new_project_name

    @guarded
    def new_project(self, widget: toga.Button, **kwargs: Any) -> None:
        def snake(s: str) -> str:
            return "_".join(s.lower().split())

        project_name = self.new_project_name.value if self.new_project_name else ""
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

    async def confirm(self, text: str, title: str) -> bool:
        """Ask a yes/no question; True if the user said yes."""
        assert isinstance(self.app.main_window, toga.MainWindow)
        return bool(await self.app.main_window.dialog(toga.QuestionDialog(title, text)))

    @property
    def site_packages(self) -> Path:
        """Where prototypes' dependencies are installed."""
        return Path(self.cache_path) / "site_packages"

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

    SETUP_PAGES: ClassVar[dict[str, str]] = {
        "packages": "Packages",
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
                    python=[
                        ("Version", platform.python_version()),
                        ("Implementation", platform.python_implementation()),
                        ("Platform", platform.platform()),
                    ],
                    bundled=pip.get_bundled_inventory(self.site_packages),
                    aliases=about.alias_rows(
                        {**pip.ALIASES, **self.configured_aliases()}
                    ),
                    health=self.health,
                    health_error=self.health_error,
                )
            case _:
                return setup_pages.permissions_html(permissions.status(self.app))

    def render_setup_page(self) -> None:
        """Redraw the open Setup page, if there is one."""
        if self.setup_page is None:
            return
        self.setup_html = without_title(
            self.setup_page_html(self.setup_page), self.SETUP_PAGES[self.setup_page]
        )
        self.load_page(self.setup_view, self.setup_html)

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
        self.remember()
        self.render_setup_page()

    @guarded
    def close_setup_page(
        self, widget: toga.Widget | None = None, **kwargs: Any
    ) -> None:
        """Back: pop the Setup page and return to the tabs."""
        self.pop_screen()
        self.setup_page = None
        self.remember()

    @staticmethod
    def menu_entry(button: toga.Button) -> toga.Box:
        """A Setup menu button filling a row of its own (#109).

        A bare button in a column is as wide as its text until the tab's
        width is known, and then stretches, so the menu looked different on
        first showing, after coming back from a page, and on iPad. In a row,
        flex=1 makes it fill the width the same way every time.
        """
        button.style.flex = 1
        return toga.Row(children=[button])

    def setup_menu_button(self, page: str) -> toga.Box:
        """A Setup menu entry that opens one of the detail pages."""
        return self.menu_entry(
            toga.Button(
                f"{self.SETUP_PAGES[page]} ›",
                on_press=lambda w: self.open_setup_page(page),
            )
        )

    @guarded
    async def handle_clear_quick_start(
        self, widget: toga.Widget, **kwargs: Any
    ) -> None:
        """Stop offering a prototype at launch."""
        current = self.settings.get_quick_start()
        if not current:
            await self.info("No Quick Start is set.", "Quick Start")
            return
        if await self.confirm(
            f"Stop offering {quick_start_name(current)} when the app opens?",
            "Clear Quick Start",
        ):
            self.settings.set_quick_start(None)
            await self.info("Quick Start cleared.", "Quick Start")

    @guarded
    def handle_open_settings(self, widget: toga.Widget, **kwargs: Any) -> None:
        """Open this app's page in the iOS Settings app."""
        if not permissions.open_app_settings():
            self.setup_activity.update("Settings can only be opened on iOS", on=False)

    @guarded
    async def handle_open_files(self, widget: toga.Widget, **kwargs: Any) -> None:
        """Open the Documents folder in the Files app (#181)."""
        folder = self.category_dirs()["Documents"]
        if not files_app.open_in_files(folder):
            await self.info(f"Couldn't open {folder} in Files.", "Files")

    @guarded
    def handle_resume_toggle(self, widget: toga.Switch, **kwargs: Any) -> None:
        """The switch for resuming where the user left off (#188)."""
        self.set_resume_enabled(bool(widget.value))

    @guarded
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

    @guarded
    async def handle_check_updates(self, widget: toga.Widget, **kwargs: Any) -> None:
        """Check user packages on PyPI, and the app's Python and bundled packages.

        The two checks are independent: if one can't be made (offline), the
        other's result is still shown.
        """
        self.setup_activity.update("Checking PyPI and python.org")
        user_message = await self.check_user_packages()
        health_message = await self.check_app_health()
        self.render_setup_page()
        self.setup_activity.update(
            "; ".join(m for m in (user_message, health_message) if m), on=False
        )

    async def check_user_packages(self) -> str:
        """Ask PyPI whether user packages have newer versions; a status line."""
        inventory = pip.get_package_inventory(self.site_packages)
        try:
            updates = await asyncio.to_thread(
                self.with_client, maintenance.find_updates, inventory
            )
        except maintenance.MaintenanceError as e:
            self.pending_updates = []
            self.update_error = str(e)
            self.update_all_button.enabled = False
            return str(e)
        self.pending_updates = updates
        self.checked_updates = updates
        self.update_error = None
        self.update_all_button.enabled = bool(updates)
        return f"{len(updates)} package update(s)" if updates else "Packages up to date"

    async def check_app_health(self) -> str:
        """Compare Python and bundled packages with python.org and PyPI."""
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
            return ""
        self.health = health
        self.health_error = None
        return f"App: {health.summary}"

    @guarded
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
                    self.new_project_field(),
                    toga.Button("Add", on_press=self.new_project),
                ],
            ),
            self.menu_entry(
                toga.Button("Environment ›", on_press=self.open_setup_environment)
            ),
            heading("Maintenance"),
            *(self.setup_menu_button(page) for page in self.SETUP_PAGES),
            heading("App"),
            self.menu_entry(
                toga.Button("Open Documents in Files", on_press=self.handle_open_files)
            ),
            toga.Switch(
                "Resume where I left off",
                value=self.resume_enabled,
                on_change=self.handle_resume_toggle,
                margin=(4, 8),
            ),
            self.menu_entry(
                toga.Button("Clear Quick Start", on_press=self.handle_clear_quick_start)
            ),
            self.menu_entry(toga.Button("Backup", on_press=self.handle_backup_press)),
            self.menu_entry(
                toga.Button(
                    "Exit",
                    visibility="visible" if exit_visible else "hidden",
                    on_press=self.do_on_done_callback,
                )
            ),
        ]

    @guarded
    def open_setup_environment(
        self, widget: toga.Widget | None = None, **kwargs: Any
    ) -> RunWithForm:
        """Setup's environment variables, inherited by every run."""
        form = RunWithForm(
            "Setup",
            args=None,
            env=self.settings.get_environment(),
            inherited=[self.system_layer()],
            show_inherited=self.show_inherited_env,
            on_show_inherited=self.set_show_inherited_env,
            screens=self,
            on_save=lambda settings: self.settings.set_environment(settings.env),
            ask=self.ask,
            tell=self.tell,
            ask_fields=self.ask_fields,
            args_note="Every script and project inherits these variables. "
            "To override them, or set arguments, swipe right on a script and "
            "choose Setup.",
            screen_title="Environment",
        )
        form.open()
        self.run_with_form = form
        return form

    # Inside your Toga App class layout or commands:
    @guarded
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
