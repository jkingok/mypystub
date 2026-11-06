"""The list's swipe actions: Info, Setup, and the README and Info screens."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import toga

from . import (
    info_pages,
    row_info,
    scan,
)
from .errors import guarded
from .pages import html_page, readme_html
from .run_settings import RunSettings, quick_start_name
from .run_with import RunWithForm
from .ui_rowsettings import RowSettingsMixin


class SwipeMixin(RowSettingsMixin):
    """Swipe left for Info, swipe right for Setup."""

    def __init__(self, host_app: toga.App, on_done: Callable[[Any], None]) -> None:
        super().__init__(host_app, on_done)
        # The README and Info screens, and the Setup form that's open
        self.readme_page = ""
        self.readme_view: toga.WebView | None = None
        self.run_with_form: RunWithForm | None = None
        self.script_list.on_primary_action = self.handle_info
        self.script_list.on_secondary_action = self.handle_run_with

    @guarded
    def handle_info(self, widget: toga.DetailedList, row: Any, **kwargs: Any) -> None:
        """Swipe left: Info."""
        asyncio.ensure_future(self.show_info(row))

    @guarded
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
                kind, title, scan.folder_summary(folder)
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
        if Path(row.project_dir).is_file():  # a zipapp is a file, not a folder
            return info_pages.zipapp_info_html(
                Path(row.project_dir), title, entry=entry, show_entries=not is_entry
            )
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

    @guarded
    def handle_run_with(
        self, widget: toga.DetailedList, row: Any, **kwargs: Any
    ) -> None:
        """Swipe right: Setup."""
        asyncio.ensure_future(self.run_with(row))

    @guarded
    async def run_with(self, row: Any) -> None:
        """Open the Setup form, or say why a row has none."""
        kind = row_info.row_type(row)
        title = str(getattr(row, "title", ""))
        if not row_info.runnable(kind) and kind != "package":
            message = row_info.run_with_message(kind, title, self.up_destination(row))
            await self.info(message, title)
            return
        self.open_run_with(row)

    async def make_quick_start(self, key: str, title: str) -> bool:
        """Offer `key` at launch; confirm first if another is already set.

        Returns whether `key` is now the Quick Start.
        """
        current = self.settings.get_quick_start()
        if current == key:
            return True
        if current and not await self.ask(
            "Quick Start",
            f"{quick_start_name(current)} is the current Quick Start. "
            f"Replace it with {title}?",
        ):
            return False
        self.settings.set_quick_start(key)
        await self.info(f"{title} will be offered when the app opens.", "Quick Start")
        return True

    def open_run_with(self, row: Any) -> RunWithForm:
        """Open the Setup form for a runnable row or a package.

        A package with several entry points has no arguments of its own and
        can't run, so its form sets only the variables its entry points inherit.
        A runnable row can also be made the Quick Start from here.
        """
        key = self.row_key(row)
        title = str(getattr(row, "title", ""))
        saved = self.settings.get_run_with(key)
        runs = row_info.runnable(row_info.row_type(row))

        def save(settings: RunSettings) -> None:
            self.settings.set_run_with(key, settings, with_args=runs)

        form = RunWithForm(
            title,
            args=saved.args if runs else None,
            env=saved.env,
            inherited=self.inherited_layers(row),
            screens=self,
            on_save=save,
            ask=self.ask,
            tell=self.tell,
            ask_fields=self.ask_fields,
            on_quick_start=(
                (lambda: self.make_quick_start(key, title)) if runs else None
            ),
            is_quick_start=runs and self.settings.get_quick_start() == key,
        )
        form.open()
        self.run_with_form = form
        return form
