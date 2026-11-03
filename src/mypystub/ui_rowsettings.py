"""Where a row's Setup is saved, and what it inherits."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import (
    row_info,
)
from .run_settings import Layer, RunSettings, merged_env, settings_key
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

    def inherited_layers(self, row: Any) -> list[Layer]:
        """The environment layers a row inherits: Setup, then its package's."""
        layers = [self.setup_layer()]
        if row_info.row_type(row) == "entry":
            package = self.settings.get_run_with(self.row_key(row, entry=False))
            layers.append(Layer(str(row.package_title), package.env))
        return layers

    def run_settings_for(self, row: Any) -> tuple[RunSettings, dict[str, str]]:
        """A runnable row's saved settings, and the environment it inherits.

        Setup's variables, then its package's, then its own: inner ones win.
        """
        own = self.settings.get_run_with(self.row_key(row))
        layers = [layer.env for layer in self.inherited_layers(row)]
        return own, merged_env([*layers, own.env])
