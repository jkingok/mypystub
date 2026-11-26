"""Where a row's Setup is saved, and what it inherits."""

from __future__ import annotations

from pathlib import Path, PurePath
from types import SimpleNamespace
from typing import Any

from . import (
    row_info,
    scan,
    workdirs,
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
            case "project" | "zipapp" | "web" | "package" | "entry":
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

    @staticmethod
    def category_key(category: str) -> str:
        """The key a category's own Setup is saved under (#308)."""
        return settings_key(category, PurePath())

    def folders_around(self, row: Any) -> list[tuple[str, str]]:
        """The folders a row sits in, outermost first, as (name, settings key) (#348).

        Only folders inside the row's category; the category is its own layer. A
        folder's own folder is left out: its Setup inherits from its parents.
        """
        if self.category is None or row_info.row_type(row) == "category":
            return []
        path = self.row_path(row)
        if path is None:
            return []
        try:
            relative = path.resolve().relative_to(self.get_category_dir().resolve())
        except ValueError:
            return []
        parents = [p for p in reversed(list(relative.parents)) if p.as_posix() != "."]
        return [
            (parent.name, settings_key(self.category, parent)) for parent in parents
        ]

    def inherited_workdir(self, row: Any) -> tuple[str, str]:
        """The working folder a row inherits, and where from (#308).

        Its package's choice, then its category's, then the category's
        built-in default.
        """
        if row_info.row_type(row) == "entry":
            package = self.settings.get_run_with(self.row_key(row, entry=False))
            if workdirs.is_valid(package.workdir):
                return str(package.workdir), str(row.package_title)
        for name, key in reversed(self.folders_around(row)):  # innermost first
            folder = self.settings.get_run_with(key)
            if workdirs.is_valid(folder.workdir):
                return str(folder.workdir), name
        category = self.category or ""
        if row_info.row_type(row) != "category":
            own = self.settings.get_run_with(self.category_key(category))
            if workdirs.is_valid(own.workdir):
                return str(own.workdir), category
        return workdirs.default_for(category), "the default"

    def workdir_for(self, row: Any) -> str:
        """The working-folder choice a run of `row` uses: its own, or inherited."""
        own = self.settings.get_run_with(self.row_key(row)).workdir
        return str(own) if workdirs.is_valid(own) else self.inherited_workdir(row)[0]

    def setup_layer(self) -> Layer:
        """Setup's environment variables, inherited by every run."""
        return Layer("Setup", self.settings.get_environment())

    def inherited_layers(self, row: Any, *, system: bool = True) -> list[Layer]:
        """The environment layers a row inherits, outermost first.

        The system's, then Setup's, then its category's (#308), then its
        package's. The system layer is for showing: it already is the process
        environment a run starts with, so a run leaves it out (`system=False`).
        """
        layers = [self.system_layer()] if system else []
        layers.append(self.setup_layer())
        if self.category is not None and row_info.row_type(row) != "category":
            category = self.settings.get_run_with(self.category_key(self.category))
            layers.append(Layer(self.category, category.env))
        for name, key in self.folders_around(row):
            layers.append(Layer(name, self.settings.get_run_with(key).env))
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
        if not key or parse_settings_key(key) is None:
            return None
        row = self.row_for_key(key)
        if row is None:
            self.settings.set_quick_start(None)
        return row

    def row_for_key(self, key: str | None) -> Any | None:
        """The runnable row a settings key names, rebuilt from disk, or None.

        None if the key is empty or malformed, or the file or project is gone,
        outside its category, not runnable, or no longer has that key. The list
        is left where it is.
        """
        parsed = parse_settings_key(key) if key else None
        if parsed is None:
            return None
        category, relative, entry = parsed
        dirs = self.category_dirs()
        if category not in dirs:
            return None
        base = dirs[category].resolve()
        target = base if relative == PurePath() else base / relative.as_posix()
        if not target.resolve().is_relative_to(base) or not target.exists():
            return None
        proto = self._scan_quick_start_target(target, entry)
        row = None if proto is None else SimpleNamespace(splash=None, **proto)
        # The saved key must round-trip, or it names something we can't run
        browsing, self.category = self.category, category
        try:
            matches = row is not None and self.row_key(row) == key
        finally:
            self.category = browsing
        return row if matches else None

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
