import asyncio
import datetime as dt
import threading
from pathlib import Path

import toga
from markdown import markdown as md

from . import data as d
from . import functions as f
from . import model as m
from . import settings as s
from . import widgets as ws
from .state import state


class Prototype:
    def __init__(self, host_app, on_done):
        self.app = host_app
        self.on_done_callback = on_done  # This is your ticket back to safety
        self.title = "Media Hub"
        state.settings = s.Settings(host_app.paths)
        state.functions = f.Functions(host_app.paths, state.settings)
        state.model = m.Model(host_app.paths, state.functions)
        self.data_path = self.app.paths.data
        self.this_path = Path(__file__).resolve().parent
        self.icon_path = self.this_path / "resources" / "icons"
        self.template_path = self.this_path / "resources" / "templates"

    async def todo(self, name):
        await self.app.main_window.dialog(toga.InfoDialog("TODO", name))

    def get_content(self):
        class EditBox(toga.Box):
            def __init__(self, stack=None, key=None, values=None):
                self.key = key or dt.datetime.now().isoformat()
                self.values = values or d.MediaMatch()
                super().__init__(
                    direction="column",
                    children=[
                        ws.LabelledText(
                            "Key",
                            # id="edit_key",
                            value_text=self.key,
                            readonly=True,
                        ),
                        ws.LabelledNumber(
                            "TMDB ID",
                            # id="edit_tmdb_id",
                            value_num=self.values.tmdb_id,
                            readonly=True,
                        ),
                        toga.Divider(),
                        ws.LabelledText(
                            "Title",
                            # id="edit_title"
                            value_text=self.values.title,
                            callback=lambda w: {self.set_value("title", w.value)},
                        ),
                        ws.LabelledText(
                            "Subtitle",
                            # id="edit_subtitle"
                            value_text=self.values.subtitle,
                            callback=lambda w: {self.set_value("subtitle", w.value)},
                        ),
                        ws.LabelledDate(
                            "Release Date",
                            # id="edit_release_date"
                            value_text=self.values.release_date,
                            callback=lambda w: {
                                self.set_value("release_date", w.value)
                            },
                        ),
                        ws.LabelledSelection(
                            "Type",
                            self.values.media_type,
                            ["movie", "tv", "unknown"],
                            # id="edit_type"
                            callback=lambda w: {self.set_value("media_type", w.value)},
                        ),
                        ws.LabelledText(
                            "Overview",
                            multiline=True,
                            # id="edit_overview",
                            value_text=self.values.overview,
                            callback=lambda w: {self.set_value("overview", w.value)},
                            flex=1,
                        ),
                        toga.Row(
                            children=[
                                toga.Button(
                                    "Back",
                                    flex=1,
                                    on_press=lambda w: {
                                        self.app.widgets[self.stack].pop()  # pyright: ignore[reportArgumentType, reportOptionalMemberAccess]
                                    },
                                ),
                                toga.Button(
                                    "Save",
                                    flex=1,
                                    on_press=lambda w: (
                                        state.model.save(self.key, self.values),  # pyright: ignore[reportAttributeAccessIssue, reportOptionalMemberAccess]
                                        self.app.widgets[self.stack].pop(),  # pyright: ignore[reportArgumentType, reportOptionalMemberAccess]
                                    ),
                                ),
                            ]
                        ),
                    ],
                    flex=1,
                )
                self.stack = stack

            def set_value(self, k, v):
                setattr(self.values, k, v)

        return toga.OptionContainer(
            content=[
                (
                    "List",
                    ws.StackContainer(
                        id="stack_list",
                        direction="column",
                        children=[
                            state.model.set_list_count_label(toga.Label("")),
                            toga.DetailedList(
                                flex=1,
                                on_refresh=lambda w: {state.model.reload_items()},  # pyright: ignore[reportArgumentType]
                                primary_action="View",
                                on_primary_action=lambda w, row: asyncio.create_task(  # pyright: ignore[reportArgumentType]
                                    self.todo("View")
                                ),
                                secondary_action="Delete",
                                on_secondary_action=lambda w, row: (  # pyright: ignore[reportArgumentType]
                                    state.model.delete(row.index)
                                ),
                                on_select=lambda w: {
                                    self.app.widgets["stack_list"].push(
                                        EditBox(
                                            "stack_list",
                                            i := w.selection.index,
                                            state.functions.get_cached_selection(i),
                                        )
                                    )
                                },
                                data=state.model.items_list_source,
                            ),
                        ],
                    ),
                    self.icon_path / "list.png",
                ),
                (
                    "Add",
                    ws.StackContainer(
                        direction="column",
                        id="stack_add",
                        children=[
                            toga.WebView(
                                flex=1, url="https://themoviedb.org", id="web_add"
                            ),
                            toga.Row(
                                children=[
                                    toga.Button(
                                        "⁠➕ Add This",
                                        flex=1,
                                        on_press=lambda w: {
                                            # ws.Utils.info_task(w, w.text, f"{r.title} added." if (r := state.model.add_from_url(url := self.app.widgets["web_add"].url)) else f"Unknown URL {url}")
                                            self.app.widgets["stack_add"].push(
                                                EditBox("stack_add", None, v)
                                            )
                                            if (
                                                v := state.model.add_from_url(
                                                    u := self.app.widgets["web_add"].url
                                                )
                                            )
                                            else ws.Utils.info_task(
                                                w, w.text, f"Unknown URL {u}"
                                            )
                                            # state.model.add_from_url(self.app.widgets["web_add"].url)
                                        },
                                    ),
                                    toga.Button(
                                        "📜 Manual Entry",
                                        flex=1,
                                        on_press=lambda w: {
                                            self.app.widgets["stack_add"].push(
                                                EditBox("stack_add")
                                            )
                                        },
                                    ),
                                ]
                            ),
                        ],
                    ),
                    self.icon_path / "add.png",
                ),
                (
                    "View",
                    toga.Column(
                        children=[
                            toga.WebView(
                                id="web_view",
                                content=c.read_text()
                                if (c := self.data_path / "catalog.html").exists()
                                else "",
                                flex=1,
                            ),
                            toga.Row(
                                children=[
                                    toga.Button(
                                        "🔄 Reload",
                                        flex=1,
                                        on_press=lambda w: threading.Thread(
                                            target=lambda: (
                                                state.functions.generate_offline_responsive_html(
                                                    state.functions.load_titles_from_cache(),
                                                    page_title=state.settings.get(
                                                        "page_title"
                                                    ),
                                                    output_path=self.data_path
                                                    / "catalog.html",
                                                ),
                                                self.app.add_background_task(
                                                    lambda _: setattr(
                                                        self.app.widgets["web_view"],
                                                        "content",
                                                        (
                                                            self.data_path
                                                            / "catalog.html"
                                                        ).read_text(),
                                                    )
                                                ),
                                            ),
                                            daemon=True,
                                        ).start(),  # Spin up the background thread worker context safely
                                    ),
                                    toga.Button(
                                        "⁠📤⁠ Share",
                                        flex=1,
                                        on_press=lambda w: ws.Utils.open_share_sheet(
                                            w, self.data_path / "catalog.html"
                                        ),
                                    ),
                                ]
                            ),
                        ]
                    ),
                    self.icon_path / "eye.png",
                ),
                (
                    "Setup",
                    toga.Column(
                        children=[
                            ws.LabelledText(
                                "Title",
                                value_text=state.settings.get("page_title"),
                                callback=lambda w: {
                                    state.settings.set("page_title", w.value)
                                },
                                confirm=lambda w: {ws.Utils.close_keyboard(w)},
                            ),
                            toga.Row(
                                children=[
                                    ws.LabelledText(
                                        "API Key",
                                        value_text=state.settings.get("tmdb_api_key"),
                                        callback=lambda w: {
                                            state.settings.set("tmdb_api_key", w.value)
                                        },
                                        confirm=lambda w: {ws.Utils.close_keyboard(w)},
                                        flex=1,
                                    ),
                                    toga.Button(
                                        "Get",
                                        on_press=lambda w: asyncio.create_task(
                                            self.todo("Go to your browser")
                                        ),
                                    ),
                                ]
                            ),
                            toga.Divider(),
                            toga.Button(
                                "Exit",
                                visibility="visible"
                                if hasattr(self.app.main_window, "content_stack")
                                and len(self.app.main_window.content_stack) > 0
                                else "hidden",
                                on_press=self.on_done_callback,
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
                                flex=1,
                            )
                        ]
                    ),
                    self.icon_path / "interrogation.png",
                ),
            ],
        )

    def exit_back(self, button):
        # Fire the parent's handler cleanly
        self.on_done_callback()
