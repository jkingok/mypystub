"""The Setup tab: its menu, detail pages and actions."""

from __future__ import annotations

import asyncio
import importlib
import platform
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

import httpx2
import toga
from packaging.utils import canonicalize_name

from togax_jkingok import LabelledActivity

from . import (
    about,
    backups,
    files_app,
    git_updates,
    maintenance,
    native,
    permissions,
    release_check,
    setup_pages,
    share_items,
    update_cache,
)
from . import piplike as pip
from .errors import guarded
from .info_pages import escape
from .pages import without_title
from .run_settings import quick_start_name
from .run_with import RunWithForm
from .ui_base import PrototypeBase
from .ui_helpers import (
    open_share_sheet,
)


class SetupMixin(PrototypeBase):
    """The Setup tab and the pages it opens."""

    def __init__(self, host_app: toga.App, on_done: Callable[[Any], None]) -> None:
        super().__init__(host_app, on_done)
        # Setup view (#77): a menu of sections, each opening a detail page (a
        # WebView, since Labels don't wrap) with native buttons for its actions
        self.setup_view = toga.WebView(
            flex=1, on_navigation_starting=self.open_external
        )
        self.setup_page: str | None = None
        self.setup_html = ""
        self.update_all_button = toga.Button(
            "Update all", on_press=self.handle_update_all, enabled=False
        )
        self.setup_activity = LabelledActivity()
        # At the foot of the Setup tab: shown only while something there works
        # in the background (Backup), so the menu itself doesn't change
        self.setup_tab_activity = LabelledActivity(display="none", margin=(4, 8))
        # A backup chosen for Restore, waiting on its preview (#303)
        self._pending_restore: tuple[Path, dict] | None = None
        self.packages_summary = ""
        self.pending_updates: list[maintenance.Update] = []
        # User packages from git that are behind their branch, and where each
        # came from (Update all installs the branch again, #328)
        self.git_user_updates: list[git_updates.GitUpdate] = []
        self.git_user_sources: dict[str, git_updates.GitSource] = {}
        # None until checked; the last check's error, if it failed
        self.checked_updates: list[maintenance.Update] | None = None
        self.update_error: str | None = None
        self.health: maintenance.Health | None = None
        self.health_error: str | None = None
        self.build_error: str | None = None  # why the newer-build check failed
        # When the shown results were found: by a check, or a remembered one
        self.last_checked: datetime | None = None

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
                    git_updates=self.git_user_updates,
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
                    build_error=self.build_error,
                    last_checked=self.last_checked,
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
                    self.iconed(
                        toga.Button(
                            "Check for updates", on_press=self.handle_check_updates
                        ),
                        "refresh.png",
                    ),
                    self.update_all_button,
                    self.iconed(
                        toga.Button(
                            "Wipe user packages…", on_press=self.handle_wipe_cache
                        ),
                        "trash.png",
                    ),
                ]
            case _:
                return [
                    self.iconed(
                        toga.Button(
                            "Open Settings", on_press=self.handle_open_settings
                        ),
                        "settings-sliders.png",
                    )
                ]

    def open_setup_page(self, page: str) -> None:
        """Show a Setup page over the launcher, with a Back button.

        It's pushed onto the window's content stack like any other view, so Back
        pops it and restores the tabs as they were.
        """
        if page == "packages":
            self.refresh_packages()
            if self.last_checked is None:
                self.show_last_check()
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
        self.push_screen(self.SETUP_PAGES[page], content, on_back=self.close_setup_page)
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

    def iconed(self, button: toga.Button, icon_file: str) -> toga.Button:
        """`button`, with a bundled icon beside its text where there is one.

        The icon files are Flaticon UIcons in resources/icons; one that hasn't
        been added yet leaves the button as text (see add_button_icon).
        """
        self.add_button_icon(button, icon_file)
        return button

    def backup_row(self) -> toga.Box:
        """Backup and Restore, side by side, with their icons (#303)."""
        backup = toga.Button("Backup", on_press=self.handle_backup_press, flex=1)
        restore = toga.Button("Restore", on_press=self.handle_restore_press, flex=1)
        return toga.Row(
            children=[
                self.iconed(backup, "backup.png"),
                self.iconed(restore, "restore.png"),
            ]
        )

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
        """Open this app's page in the Settings app (iOS) or system settings (Android)."""
        if not permissions.open_app_settings():
            self.setup_activity.update("Settings couldn't be opened", on=False)

    @guarded
    async def handle_open_files(self, widget: toga.Widget, **kwargs: Any) -> None:
        """Open the Documents folder in the Files app (#181)."""
        folder = self.category_dirs()["Documents"]
        if not files_app.open_in_files(folder):
            await self.info(f"Couldn't open {folder} in Files.", "Files")

    @guarded
    def handle_preserve_logs_toggle(self, widget: toga.Switch, **kwargs: Any) -> None:
        """The switch for keeping the log between launches (#198)."""
        self.set_preserve_logs(bool(widget.value))

    @guarded
    def handle_native_toggle(self, widget: toga.Switch, **kwargs: Any) -> None:
        """Desktop only: the real pip and Python, or the mobile ways (#280)."""
        self.set_native_mode(bool(widget.value))

    @guarded
    def handle_console_toggle(self, widget: toga.Switch, **kwargs: Any) -> None:
        """Show runs in toga-console instead of the usual output (experimental)."""
        self.set_experimental_console(bool(widget.value))

    @guarded
    def handle_resume_toggle(self, widget: toga.Switch, **kwargs: Any) -> None:
        """The switch for resuming where the user left off (#188)."""
        self.set_resume_enabled(bool(widget.value))

    @guarded
    async def handle_wipe_cache(self, widget: toga.Widget, **kwargs: Any) -> None:
        """Delete user-installed packages, after confirmation."""
        if not await self.confirm(
            "Delete all user-installed packages (and, on a desktop, Native "
            "mode's venv)? Prototypes reinstall their dependencies on their "
            "next run, which needs the network.",
            "Wipe user packages",
        ):
            return
        await asyncio.to_thread(maintenance.wipe, self.site_packages)
        if native.available():
            # Native mode's venv holds what pip installed (#280): remade next run
            await asyncio.to_thread(
                maintenance.wipe, Path(self.cache_path) / native.VENV_FOLDER
            )
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
        other's result is still shown. Each request is counted on the progress
        bar: one per package, plus GitHub's Releases and python.org.
        """
        self.setup_activity.update("Checking PyPI and python.org")
        user = pip.get_package_inventory(self.site_packages)
        bundled = pip.get_bundled_inventory(self.site_packages)
        tick = self.check_counter(len(user) + len(bundled) + 2)
        # Answers given today are used again: each package is asked about at
        # most once a day per version
        cache = self.new_update_cache()
        user_message = await self.check_user_packages(tick, cache)
        health_message = await self.check_app_health(tick, cache)
        self.last_checked = datetime.now()
        await asyncio.to_thread(cache.save, self.last_checked)
        self.render_setup_page()
        self.setup_activity.update(
            "; ".join(m for m in (user_message, health_message) if m), on=False
        )

    def check_counter(self, total: int) -> Callable[[str], None]:
        """A tick for each check made, from any thread: "Checking <name>", n/total.

        The checks run one after another, so the count needs no lock.
        """
        done = [0]

        def show(name: str, number: int) -> None:
            self.setup_activity.update(f"Checking {name}")
            self.setup_activity.count(number, total)

        def tick(name: str) -> None:
            self.app.loop.call_soon_threadsafe(show, name, done[0])
            done[0] += 1

        return tick

    def new_update_cache(self) -> update_cache.UpdateCache:
        """The remembered answers of earlier checks, fresh for today."""
        return update_cache.UpdateCache(Path(self.cache_path) / update_cache.CACHE_NAME)

    def show_last_check(self) -> None:
        """Show the last check's results, as remembered, without asking anyone.

        Packages with no remembered answer are left out until the next check.
        """
        cache = self.new_update_cache()
        if cache.checked is None:
            return
        bundled = pip.get_bundled_inventory(self.site_packages)
        no_client: Any = None  # offline: nothing is asked
        updates = self.user_check(no_client, None, cache, offline=True)
        self.pending_updates = self.checked_updates = updates
        self.update_all_button.enabled = bool(updates or self.git_user_updates)
        self.health = self.health_check(no_client, bundled, None, None, cache, True)
        self.last_checked = cache.checked

    async def check_user_packages(
        self,
        tick: Callable[[str], None] | None = None,
        cache: update_cache.UpdateCache | None = None,
    ) -> str:
        """Ask PyPI whether user packages have newer versions; a status line.

        User packages installed from git are asked about on their branch.
        """
        try:
            updates = await asyncio.to_thread(
                self.with_client,
                lambda client: self.user_check(client, tick, cache),
            )
        except maintenance.MaintenanceError as e:
            self.pending_updates = []
            self.update_error = str(e)
            self.update_all_button.enabled = False
            return str(e)
        self.pending_updates = updates
        self.checked_updates = updates
        self.update_error = None
        found = len(updates) + len(self.git_user_updates)
        self.update_all_button.enabled = bool(found)
        return f"{found} package update(s)" if found else "Packages up to date"

    def user_check(
        self,
        client: httpx2.Client,
        tick: Callable[[str], None] | None,
        cache: update_cache.UpdateCache | None,
        offline: bool = False,
    ) -> list[maintenance.Update]:
        """User packages with newer versions on PyPI; from git, newer commits.

        The git ones are kept in ``git_user_updates`` (and their sources in
        ``git_user_sources``); the PyPI ones are returned.
        """
        inventory = pip.get_package_inventory(self.site_packages)
        names = {canonicalize_name(name) for name in inventory}
        from_git = {
            name: source
            for name, source in git_updates.git_sources(
                [str(self.site_packages)]
            ).items()
            if name in names
        }
        from_pypi = {
            name: version
            for name, version in inventory.items()
            if canonicalize_name(name) not in from_git
        }
        updates = maintenance.find_updates(
            client, from_pypi, on_check=tick, cache=cache, offline=offline
        )
        self.git_user_updates = git_updates.find_git_updates(
            client, from_git, on_check=tick, cache=cache, offline=offline
        )
        self.git_user_sources = from_git
        return updates

    async def check_app_health(
        self,
        tick: Callable[[str], None] | None = None,
        cache: update_cache.UpdateCache | None = None,
    ) -> str:
        """Is this the latest build? If so, check Python and the bundled packages.

        GitHub's Releases are asked first: one cheap request. If a newer build
        exists it is what fixes everything else, so python.org and PyPI are not
        asked. If GitHub can't be reached the other checks still run.
        """
        build = None
        self.build_error = None
        if tick is not None:
            tick("GitHub Releases")
        try:
            build = await asyncio.to_thread(
                self.with_client, release_check.check_build, self.app.version
            )
        except maintenance.MaintenanceError as e:
            self.build_error = str(e)
        if build is not None and build.newer:
            self.health = maintenance.Health(None, [], build)
            self.health_error = None
            return f"App: {self.health.summary}"
        bundled = pip.get_bundled_inventory(self.site_packages)

        def check(client: httpx2.Client) -> maintenance.Health:
            return self.health_check(client, bundled, build, tick, cache)

        try:
            health = await asyncio.to_thread(self.with_client, check)
        except maintenance.MaintenanceError as e:
            self.health_error = str(e)
            return ""
        self.health = health
        self.health_error = None
        return f"App: {health.summary}"

    def health_check(
        self,
        client: httpx2.Client,
        bundled: dict[str, str],
        build: Any,
        tick: Callable[[str], None] | None,
        cache: update_cache.UpdateCache | None,
        offline: bool = False,
    ) -> maintenance.Health:
        """Python and the bundled packages, compared with what's newest.

        Packages bundled from git (Toga, toga-console) are compared with their
        branch instead of their version with PyPI (#328).
        """
        from_git = git_updates.bundled_from_git(bundled)
        from_pypi = {
            name: version
            for name, version in bundled.items()
            if canonicalize_name(name) not in from_git
        }
        if tick is not None:
            tick("python.org")
        python = maintenance.check_python_cached(
            client, platform.python_version(), cache, offline
        )
        updates = maintenance.find_updates(
            client,
            from_pypi,
            critical=maintenance.APP_CRITICAL,
            on_check=tick,
            cache=cache,
            offline=offline,
        )
        newer = git_updates.find_git_updates(
            client,
            from_git,
            critical=maintenance.APP_CRITICAL,
            on_check=tick,
            cache=cache,
            offline=offline,
        )
        return maintenance.Health(python, updates, build, newer)

    @guarded
    async def handle_update_all(self, widget: toga.Widget, **kwargs: Any) -> None:
        """Install the versions found by the last update check.

        Packages from git are installed from their branch again, at its newest
        commit.
        """
        if not self.pending_updates and not self.git_user_updates:
            return
        requirements = maintenance.upgrade_requirements(self.pending_updates) + [
            git_updates.requirement_for(self.git_user_sources[u.name])
            for u in self.git_user_updates
            if u.name in self.git_user_sources
        ]
        try:
            await pip.resolve_and_install_async(
                requirements,
                self.site_packages,
                on_progress=self.setup_activity.update,
                on_count=self.setup_activity.count,
            )
        except Exception as e:  # noqa: BLE001
            self.setup_activity.update("Update failed", on=False)
            await self.error(str(e), "Update failed")
            return
        self.pending_updates = []
        self.checked_updates = []
        self.git_user_updates = []
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
            heading("Running"),
            self.menu_entry(
                toga.Button("Environment ›", on_press=self.open_setup_environment)
            ),
            heading("Maintenance"),
            *(self.setup_menu_button(page) for page in self.SETUP_PAGES),
            heading("App"),
            self.menu_entry(
                self.iconed(
                    toga.Button(
                        "Open Documents in Files", on_press=self.handle_open_files
                    ),
                    "folder.png",
                )
            ),
            *(
                [
                    toga.Switch(
                        "Native mode (pip and a separate Python)",
                        value=self.native_mode,
                        on_change=self.handle_native_toggle,
                        margin=(4, 8),
                    )
                ]
                if native.available()
                else []
            ),
            toga.Switch(
                "Experimental Console",  # Help says it applies from the next run
                value=self.experimental_console,
                on_change=self.handle_console_toggle,
                margin=(4, 8),
            ),
            toga.Switch(
                "Preserve Logs",
                value=self.preserve_logs,
                on_change=self.handle_preserve_logs_toggle,
                margin=(4, 8),
            ),
            toga.Switch(
                "Resume where I left off",
                value=self.resume_enabled,
                on_change=self.handle_resume_toggle,
                margin=(4, 8),
            ),
            self.menu_entry(
                self.iconed(
                    toga.Button(
                        "Clear Quick Start", on_press=self.handle_clear_quick_start
                    ),
                    "broom.png",
                )
            ),
            self.backup_row(),
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
            inherited_icon=self.inherited_icon,
            screens=self,
            on_save=lambda settings: self.settings.set_environment(settings.env),
            ask=self.ask,
            tell=self.tell,
            ask_fields=self.ask_fields,
            # The screen's title says what it is, and the Setup tab already
            # has an Environment heading: no note, and no section to fold
            args_note=None,
            collapsible_sections=False,
            screen_title="Environment",
        )
        form.open()
        self.run_with_form = form
        return form

    @guarded
    async def handle_backup_press(self, widget: toga.Button, **kwargs: Any) -> None:
        """Back up Documents and the settings to one zip, then share it (#303).

        It's made on a worker thread, so the app stays responsive, and the
        button is off until it's done. The cache isn't included: it is all
        made again as needed.
        """
        widget.enabled = False
        self.show_setup_tab_activity("Backing up…")
        try:
            archive = await asyncio.to_thread(
                backups.create,
                Path(self.data_path),
                Path(self.app.paths.config),
                Path(self.app.paths.cache) / share_items.SHARE_FOLDER,
                str(self.app.formal_name),
                str(self.app.version or ""),
            )
        except OSError as error:
            await self.error(f"Couldn't make the backup: {error}", "Backup Failed")
            return
        finally:
            widget.enabled = True
            self.show_setup_tab_activity(None)
        open_share_sheet(widget, archive)

    def show_setup_tab_activity(self, text: str | None) -> None:
        """Show `text` with a spinner at the foot of the Setup tab, or hide it.

        The button that started the work keeps its own label and icon.
        """
        activity = self.setup_tab_activity
        activity.update(text or "", on=text is not None)
        activity.style.display = "pack" if text is not None else "none"

    @guarded
    async def handle_restore_press(self, widget: toga.Button, **kwargs: Any) -> None:
        """Restore a backup from the clipboard, as Paste takes things (#303).

        Only a MyPyStub backup (a zip with its manifest) is accepted. Its
        preview says what it holds; Restore then puts it back, keeping what it
        replaces in backups/.
        """
        from . import bridge

        try:
            content = await bridge.read_pasteboard(
                Path(self.app.paths.cache) / "restore"
            )
        except (OSError, ValueError) as error:
            await self.error(f"Couldn't read the backup: {error}", "Restore")
            return
        if content is None or content[0] != "file":
            await self.info(
                "Copy a MyPyStub backup (the .zip that Backup shared) in the "
                "Files app, then press Restore.",
                "Nothing to restore",
            )
            return
        archive = Path(content[1])
        try:
            manifest = await asyncio.to_thread(backups.read_manifest, archive)
        except backups.BackupProblem as problem:
            await self.error(str(problem), "Not a backup")
            return
        self._pending_restore = (archive, manifest)
        body = f"<h1>{escape(archive.name)}</h1>\n" + "".join(
            f"<p>{escape(line)}</p>\n" for line in backups.summary(manifest)
        )
        body += (
            "<p>What a restored item replaces is kept in its folder's "
            "<code>backups</code>, as with Paste.</p>"
        )
        view = toga.WebView(flex=1, on_navigation_starting=self.open_external)
        self.load_page(view, body)
        top = toga.Row(
            children=[
                toga.Button("✕ Cancel", on_press=self.cancel_restore),
                toga.Box(flex=1),
                toga.Button("Restore", on_press=self.confirm_restore),
            ]
        )
        self.push_screen(
            "Restore", toga.Column(children=[top, view]), on_back=self.cancel_restore
        )

    @guarded
    def cancel_restore(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Leave the backup alone."""
        self._pending_restore = None
        self.pop_screen()

    @guarded
    async def confirm_restore(
        self, widget: toga.Widget | None = None, **kwargs: Any
    ) -> None:
        """Put the previewed backup back."""
        pending = self._pending_restore
        self._pending_restore = None
        self.pop_screen()
        if pending is None:
            return
        archive, manifest = pending
        settings = bool(manifest.get("config")) and await self.confirm(
            "Also replace your settings (Setup, aliases and each script's run "
            "settings) with the backup's? Yours are kept in backups/.",
            "Restore settings",
        )
        try:
            done = await asyncio.to_thread(
                backups.restore,
                archive,
                Path(self.data_path),
                Path(self.app.paths.config),
                settings=settings,
            )
        except (OSError, ValueError) as error:
            await self.error(f"Couldn't restore: {error}", "Restore")
            return
        if done.config:
            self.settings.config_doc = self.settings._load()
        self.reload_menu(self.script_list)
        await self.info(restored_message(done), "Restored")


def restored_message(done: backups.Restored) -> str:
    """What a restore did, in a sentence or two."""
    parts = []
    if done.added:
        parts.append(f"Added {', '.join(done.added)}.")
    if done.replaced:
        parts.append(
            f"Replaced {', '.join(done.replaced)}; the versions they replaced are "
            "in backups/."
        )
    if done.unchanged:
        parts.append(f"{', '.join(done.unchanged)} already matched the backup.")
    if done.config:
        parts.append("Settings restored.")
    return " ".join(parts) or "There was nothing to restore."
