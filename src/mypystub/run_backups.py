"""The backups section of a row's Setup: swipe a backup to restore or delete it (#182).

A switch shows or hides it (hidden each time Setup opens, since the Setup
screen is crowded). Each backup is a row: swipe left to delete it (the list's
primary action), right to restore it (the secondary one); both ask first.
Backups are made by Paste; see :mod:`versions`. Restoring backs up what is
current first. Settings are never touched: they are keyed by the item's path,
which restoring keeps.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import toga

from . import versions
from .errors import guarded
from .maintenance import human_size
from .run_with import collapsible, fit_list, show_body

Ask = Callable[[str, str], Awaitable[bool]]
Tell = Callable[[str, str], Awaitable[None]]


class BackupsSection:
    """Backup versions of one script, zipapp or project folder."""

    def __init__(
        self,
        item: Path,
        *,
        ask: Ask,
        tell: Tell,
        on_change: Callable[[], None] = lambda: None,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.item = item
        self.ask = ask
        self.tell = tell
        self.on_change = on_change
        self.now = now
        self.found: list[versions.Backup] = []
        self.list = toga.DetailedList(
            primary_action="Delete",
            secondary_action="Restore",
            on_primary_action=self.swipe_delete,
            on_secondary_action=self.swipe_restore,
        )
        self.switch, self.details = collapsible(
            "Backup versions",
            [self.list],
            open=False,
            on_change=self.toggle,
        )
        self.content = toga.Column(children=[self.switch, self.details])
        self.refresh()

    def backup_for(self, row: Any) -> versions.Backup | None:
        """The backup a list row stands for, if it is still there."""
        try:
            return self.found[self.list.data.index(row)]
        except (ValueError, IndexError):
            return None

    def refresh(self) -> None:
        """Re-read the backups and redraw the section."""
        self.found = versions.list_backups(self.item)
        self.list.data = [
            {
                "title": f"{b.when:%Y-%m-%d %H:%M:%S}",
                "subtitle": f"{'Project folder (zip)' if b.is_folder else 'File'}"
                f" · {human_size(b.size)}",
            }
            for b in self.found
        ]
        count = len(self.found)
        self.switch.text = f"Backup versions ({count})" if count else "Backup versions"
        self.switch.enabled = count > 0 or bool(self.switch.value)
        fit_list(self.list, count)
        show_body(self.switch, self.details, has_rows=count > 0)

    async def report_error(self, error: Exception, where: str) -> None:
        """Where :func:`guarded` reports an error from one of the handlers."""
        await self.tell("Error", f"{type(error).__name__}: {error}\n\n(in {where})")

    @guarded
    def toggle(self, widget: toga.Switch, **kwargs: Any) -> None:
        self.refresh()

    @guarded
    def swipe_restore(self, widget: toga.DetailedList, row: Any, **kwargs: Any) -> None:
        backup = self.backup_for(row)
        if backup is not None:
            asyncio.ensure_future(self.restore(backup))

    @guarded
    def swipe_delete(self, widget: toga.DetailedList, row: Any, **kwargs: Any) -> None:
        backup = self.backup_for(row)
        if backup is not None:
            asyncio.ensure_future(self.delete(backup))

    async def restore(self, backup: versions.Backup) -> None:
        """Make `backup` current, after asking."""
        if not await self.ask(
            "Restore",
            f"Make the backup from {backup.when:%Y-%m-%d %H:%M:%S} the current "
            f"{self.item.name}? What is current is kept as another backup.",
        ):
            return
        try:
            versions.restore(backup.path, self.item, self.now())
        except (OSError, ValueError) as error:
            await self.tell("Restore", f"Couldn't restore: {error}")
            return
        self.refresh()
        self.on_change()
        await self.tell("Restore", f"Restored {self.item.name}.")

    async def delete(self, backup: versions.Backup) -> None:
        """Delete `backup` for good, after asking."""
        if not await self.ask("Delete", "Delete this backup for good?"):
            return
        try:
            versions.delete(backup.path)
        except (OSError, ValueError) as error:
            await self.tell("Delete", f"Couldn't delete: {error}")
            return
        self.refresh()
