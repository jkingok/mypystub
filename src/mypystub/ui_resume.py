"""Saving where the user is, so the launcher can look as if it resumed (#188)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import resume
from .ui_base import PrototypeBase


class ResumeMixin(PrototypeBase):
    """Writes the resume state whenever the tab, folder or page changes."""

    def resume_extras(self) -> dict[str, str | None]:
        """Page names only the whole launcher knows: ``setup_page``, ``help_page``.

        The launcher's top class provides them; the other mixins don't see
        each other's screens.
        """
        return {}

    def resume_snapshot(self) -> resume.Resume:
        """Where the user is now."""
        category_dir = self.category_dirs().get(self.category or "")
        package = ""
        if category_dir is not None and self.package_dir is not None:
            try:
                package = (
                    Path(self.package_dir).resolve().relative_to(category_dir.resolve())
                ).as_posix()
            except ValueError:
                package = ""
        running = self.resume_running
        extras = self.resume_extras()
        current: Any = self.tabs.current_tab if self.tabs is not None else None
        return resume.Resume(
            version=str(self.app.version or ""),
            tab=str(getattr(current, "text", "List")),
            category=self.category,
            folder=self.subfolder.as_posix() if self.subfolder != Path() else "",
            package="" if package == "." else package,
            setup_page=extras.get("setup_page"),
            help_page=extras.get("help_page"),
            running=running[0] if running else None,
            running_title=running[1] if running else "",
        )

    def remember(self) -> None:
        """Save where the user is, if it has changed. Never raises."""
        if not self.resume_ready or not self.resume_enabled:
            return
        try:
            state = self.resume_snapshot()
        except Exception as error:  # noqa: BLE001 - saving must never break the UI
            print(f"Couldn't work out where to resume: {error}")
            return
        if state != self._resume_written and resume.save(self.resume_path, state):
            self._resume_written = state
