"""Where a row's Setup is saved, and what it inherits."""

from __future__ import annotations

from pathlib import Path, PurePath
from types import SimpleNamespace
from typing import Any

from . import (
    row_info,
    scan,
)
from .run_settings import (
    EnvValue,
    Layer,
    RunSettings,
    merged_env,
    parse_settings_key,
    settings_key,
)
from .ui_base import PrototypeBase


class RowSettingsMixin(PrototypeBase):
    """Row keys and the layered settings that running and the swipes both use."""

    def row_path(self, row: Any) -> Path | None:
        """The file or folder a row stands for."""
        match row_info.row_type(row):
            case "category":
                return self.category_dirs()[row.category]
            case "folder":
                return Path(row.folder)
            case "script":
                return Path(row.entry_point)
            case "project" | "zipapp" | "package" | "entry":
                return Path(row.project_dir)
            case _:
                return None

    def row_key(self, row: Any, *, entry: bool = True) -> str:
        """The key a row's settings are saved under: its path in its category.

        An entry point inside a package adds its name to the package's path,
        unless `entry` is False, which gives the package's own key.
        """
        path = self.row_path(row)
        assert self.category is not None and path is not None
        base = self.get_category_dir().resolve()
        try:
            relative = path.resolve().relative_to(base)
        except ValueError:
            relative = Path(path.name)
        name = None
        if entry and row_info.row_type(row) == "entry":
            name = row.entry.name
        return settings_key(self.category, relative, name)

    def up_destination(self, row: Any) -> str:
        """Where a ".." row leads, for messages."""
        if getattr(row, "categories", False) or self.category is None:
            return "the categories"
        if getattr(row, "package_up", False):
            return self.current_folder_name()
        parent = self.subfolder.parent
        if parent == Path():
            return self.category
        return f"{self.category}/{parent.as_posix()}"

    def setup_layer(self) -> Layer:
        """Setup's environment variables, inherited by every run."""
        return Layer("Setup", self.settings.get_environment())

    def inherited_layers(self, row: Any, *, system: bool = True) -> list[Layer]:
        """The environment layers a row inherits, outermost first.

        The system's, then Setup's, then its package's. The system layer is
        for showing: it already is the process environment a run starts with,
        so a run leaves it out (`system=False`).
        """
        layers = [self.system_layer()] if system else []
        layers.append(self.setup_layer())
        if row_info.row_type(row) == "entry":
            package = self.settings.get_run_with(self.row_key(row, entry=False))
            layers.append(Layer(str(row.package_title), package.env))
        return layers

    def run_settings_for(self, row: Any) -> tuple[RunSettings, dict[str, EnvValue]]:
        """A runnable row's saved settings, and the changes it makes to the environment.

        Setup's variables, then its package's, then its own: inner ones win. A
        value of None means the variable is unset for the run.
        """
        own = self.settings.get_run_with(self.row_key(row))
        layers = [layer.env for layer in self.inherited_layers(row, system=False)]
        return own, merged_env([*layers, own.env])

    def resolve_quick_start(self) -> Any | None:
        """The row the Quick Start points at, or None.

        Rebuilds the row from the file or project on disk, leaving the list
        where it is: nothing moves unless the user chooses to run it. A missing,
        malformed or stale target clears the setting and returns None, so a
        deleted script can never block launch.
        """
        key = self.settings.get_quick_start()
        parsed = parse_settings_key(key) if key else None
        if parsed is None:
            return None
        category, relative, entry = parsed
        dirs = self.category_dirs()
        if category not in dirs:
            self.settings.set_quick_start(None)
            return None
        base = dirs[category].resolve()
        target = base if relative == PurePath() else base / relative.as_posix()
        if not target.resolve().is_relative_to(base) or not target.exists():
            self.settings.set_quick_start(None)
            return None
        proto = self._scan_quick_start_target(target, entry)
        row = None if proto is None else SimpleNamespace(splash=None, **proto)
        # The saved key must round-trip, or it names something we can't run
        browsing, self.category = self.category, category
        try:
            matches = row is not None and self.row_key(row) == key
        finally:
            self.category = browsing
        if not matches:
            self.settings.set_quick_start(None)
            return None
        return row

    def open_quick_start_folder(self) -> None:
        """Move the list to the folder holding the Quick Start."""
        parsed = parse_settings_key(self.settings.get_quick_start() or "")
        if parsed is not None:
            category, relative, _ = parsed
            self.show_category(category)
            self.subfolder = Path(relative.parent)

    def _scan_quick_start_target(
        self, target: Path, entry: str | None
    ) -> dict[str, Any] | None:
        """Describe a Quick Start target as a runnable row, or None."""
        try:
            if target.is_file() and target.suffix == ".py":
                proto = scan.scan_script(target)
            elif target.is_file() and target.suffix == ".pyz":
                proto = scan.scan_zipapp(target)
            elif target.is_dir() and (target / "pyproject.toml").exists():
                proto = scan.scan_project(target)
            else:
                return None
        except (OSError, ValueError):
            return None
        if proto is None:
            return None
        if entry is None:
            # A package (several entry points) opens like a folder, so can't run
            return None if proto.get("kind") == "package" else proto
        if proto.get("kind") == "package":
            matches = [r for r in scan.entry_rows(proto) if r["entry"].name == entry]
            return matches[0] if matches else None
        single = proto.get("entry")
        return proto if single is not None and single.name == entry else None
