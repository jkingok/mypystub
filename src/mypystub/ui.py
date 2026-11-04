"""The launcher: Prototype combines the feature mixins and builds the tabs."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import toga
from toga.style import Pack

from . import (
    about,
    first_run,
)
from .pages import help_html
from .ui_actions import ActionsMixin
from .ui_helpers import (
    is_ipad_from_window,
    open_share_sheet,
)
from .ui_run import RunMixin
from .ui_setup import SetupMixin
from .ui_swipe import SwipeMixin
from .ui_widgets import LabelledSelection, NotAnOptionContainer, refresh_on_new_width


class Prototype(RunMixin, SwipeMixin, ActionsMixin, SetupMixin):
    """The launcher's state and screens, built from the feature mixins."""

    def __init__(self, host_app: toga.App, on_done: Callable[[Any], None]) -> None:
        super().__init__(host_app, on_done)
        self.help_selection = LabelledSelection(
            "Show",
            items=["Help", "What's New", "About"],
            on_change=self.show_help_page,
        )
        # Links (the About page's Source) open in the browser, not in place
        self.help_view = toga.WebView(flex=1, on_navigation_starting=self.open_external)
        self.about_share = toga.Button(
            "Share", on_press=self.handle_about_share, visibility="hidden"
        )
        self.log_text = toga.MultilineTextInput(
            readonly=True,
            style=Pack(flex=1),
        )

    def reload_logs(self, widget: toga.Widget, **kwargs: Any) -> None:
        if log_path := getattr(sys.stdout, "path", None):
            logs = log_path.read_text()
            self.log_text.value = logs

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

    def choose_start_tab(self) -> str:
        """Choose the tab to open on from the version last run (#125, #126).

        - A user who has never run the app opens on Help.
        - The first time a new version is opened, Help shows "What's New".
        - Otherwise, and if the version can't be recorded (every start would
          then look new), the List, as before.

        The running version is recorded for next time. Returns the name of the
        tab that is showing.
        """
        version = self.app.version
        state = first_run.start_state(Path(self.cache_path), version)
        recorded = first_run.record_version(Path(self.cache_path), version)
        # If the version can't be recorded, every start would look like a first
        if recorded and state is first_run.StartState.NEW:
            self.help_selection.selection.value = "Help"
            self.tabs.current_tab = "Help"
        elif recorded and state is first_run.StartState.UPDATED:
            # The first time a new version is opened, show what changed in it
            self.help_selection.selection.value = "What's New"
            self.tabs.current_tab = "Help"
        current: Any = self.tabs.current_tab  # an OptionContainer's tab, or ours
        return str(current.text)

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
            home_page=self.app.home_page,
        )

    def show_help_page(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        if str(self.help_selection.value) == "About":
            body = about.to_html(self.about_sections())
            # open_share_sheet() is only implemented on iOS
            self.about_share.style.visibility = (
                "visible" if sys.platform == "ios" else "hidden"
            )
        elif str(self.help_selection.value) == "What's New":
            changes = self.template_path / "changes.md"
            text = changes.read_text(encoding="utf-8") if changes.exists() else ""
            if any(line.startswith("## ") for line in text.splitlines()):
                body = help_html(text)
            else:
                body = "<h1>What's New</h1>\n<p>Nothing new to report yet.</p>"
            self.about_share.style.visibility = "hidden"
        else:
            help_md = self.template_path / "help.md"
            body = help_html(help_md.read_text()) if help_md.exists() else ""
            self.about_share.style.visibility = "hidden"
        self.load_page(self.help_view, body)

    def handle_about_share(self, widget: toga.Button, **kwargs: Any) -> None:
        try:
            report = Path(self.cache_path) / "about.txt"
            report.write_text(about.to_text(self.about_sections()), encoding="utf-8")
            open_share_sheet(widget, report)
        except Exception as e:  # noqa: BLE001
            asyncio.create_task(
                self.error(f"Could not share environment details: {e}", "Share")
            )

    def choose_container(self, *args: Any, **kwargs: Any) -> toga.Widget:
        assert isinstance(self.app.main_window, toga.MainWindow)
        if is_ipad_from_window(self.app.main_window):
            return NotAnOptionContainer(*args, **kwargs)
        else:
            return toga.OptionContainer(*args, **kwargs)

    def setup_scroll(self) -> toga.ScrollContainer:
        """The Setup tab's menu, which scrolls on small screens."""
        scroll = toga.ScrollContainer(
            horizontal=False,
            flex=1,
            content=toga.Column(margin=(0, 8), children=self.setup_sections()),
        )
        if sys.platform == "ios":
            refresh_on_new_width(
                scroll._impl.document_container, cast(Any, scroll.content).refresh
            )
        return scroll

    def get_content(self) -> toga.Widget:
        # return toga.OptionContainer(
        self.tabs = self.choose_container(
            id="tabs",
            content=[
                (
                    "List",
                    toga.Column(children=[self.list_actions(), self.script_list]),
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
                    toga.Column(children=[self.setup_scroll()]),
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
