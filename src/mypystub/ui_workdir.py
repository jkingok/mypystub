"""Choosing a run's working folder: Inherit, Script's folder, Cache, or Documents (#308).

A pushed screen with the choices as a list. Cache is one choice and is never
browsed or shown; Documents is browsed folder by folder, and its current
folder is picked with the button at the bottom. Nothing else on the device
is offered.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import toga

from . import workdirs
from .errors import guarded
from .ui_base import PrototypeBase

INHERIT, SCRIPT, CACHE, UP = "inherit", "script", "cache", "up"


class WorkdirPickerMixin(PrototypeBase):
    """The working-folder picker, for the Setup forms."""

    async def pick_workdir(
        self, current: str | None, *, can_inherit: bool = True
    ) -> tuple[bool, str | None]:
        """Ask for a working folder; (whether chosen, the choice or None to inherit)."""
        answer: asyncio.Future[tuple[bool, str | None]] = (
            asyncio.get_running_loop().create_future()
        )
        documents = self.category_dirs()["Documents"]
        state = {"folder": Path()}  # within Documents
        rows = toga.DetailedList(flex=1)
        where = toga.Label("", margin=(4, 8))
        use = toga.Button("Use this folder", flex=1)

        def finish(value: tuple[bool, str | None]) -> None:
            if not answer.done():
                answer.set_result(value)
                self.pop_screen()

        def show() -> None:
            folder = state["folder"]
            data: list[dict[str, Any]] = []
            if folder == Path():
                if can_inherit:
                    data.append(
                        {"title": "Inherit", "subtitle": "Use the folder set above"}
                    )
                data.append(
                    {"title": "Script's folder", "subtitle": "Where the script is"}
                )
                data.append(
                    {
                        "title": "Cache",
                        "subtitle": "A folder of its own; may be cleared",
                    }
                )
            else:
                data.append({"title": "..", "subtitle": "Up a folder"})
            data += [
                {"title": f"{child.name} ›", "subtitle": "Folder"}
                for child in sorted((documents / folder).iterdir())
                if child.is_dir() and not child.name.startswith((".", "backups"))
            ]
            rows.data = data
            where.text = workdirs.describe(workdirs.documents(folder.as_posix()))
            use.text = f"Use {where.text}"

        @guarded
        def picked(widget: toga.DetailedList, **kwargs: Any) -> None:
            row = widget.selection
            if row is None:
                return
            title = str(getattr(row, "title", ""))
            if title == "Inherit":
                finish((True, None))
            elif title == "Script's folder":
                finish((True, workdirs.SCRIPT))
            elif title == "Cache":
                finish((True, workdirs.CACHE))
            elif title == "..":
                state["folder"] = state["folder"].parent
                show()
            else:
                state["folder"] = state["folder"] / title.removesuffix(" ›")
                show()

        rows.on_select = picked
        use.on_press = lambda w: finish(
            (True, workdirs.documents(state["folder"].as_posix()))
        )
        cancel = toga.Button("✕ Cancel", on_press=lambda w: finish((False, current)))
        show()
        current_text = toga.Label(
            "Now: " + (workdirs.describe(current) if current else "inherited"),
            margin=(4, 8),
        )
        self.push_screen(
            "Working folder",
            toga.Column(
                flex=1,
                children=[
                    toga.Row(children=[cancel]),
                    current_text,
                    rows,
                    where,
                    toga.Row(margin=4, children=[use]),
                ],
            ),
            on_back=lambda: finish((False, current)),
        )
        return await answer
