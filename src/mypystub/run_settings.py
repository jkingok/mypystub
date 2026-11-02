"""Saved per-thing Setup settings: command-line arguments and environment variables.

Environment variables are inherited in layers, each overriding the one before:
the process environment, then Setup, then the package, then the entry point or
script. Arguments belong to one runnable thing and are not inherited.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Any, Literal

ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

Move = Literal["top", "up", "down", "bottom"]
MOVES: tuple[Move, ...] = ("top", "up", "down", "bottom")


@dataclass
class RunSettings:
    """The arguments and environment variables saved for one thing."""

    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_table(cls, table: Mapping[str, Any] | None) -> RunSettings:
        """Read settings from a TOML table, ignoring anything malformed."""
        table = table or {}
        args = table.get("args", [])
        env = table.get("env", {})
        return cls(
            args=[str(a) for a in args] if isinstance(args, list) else [],
            env=usable_env(env) if isinstance(env, Mapping) else {},
        )

    def to_table(self, *, with_args: bool = True) -> dict[str, Any]:
        """The settings as a TOML table; `with_args` False saves the environment only."""
        table: dict[str, Any] = {}
        if with_args:
            table["args"] = list(self.args)
        table["env"] = dict(sorted_env(self.env))
        return table


def settings_key(category: str, relative: PurePath, entry: str | None = None) -> str:
    """The key settings are saved under: the thing's path within its category.

    Paths are relative to the category's root because iOS moves the app's
    bundle and data folders between installs. An entry point inside a package
    adds ``:entry`` to the package's path.
    """
    path = relative.as_posix()
    key = category if path in ("", ".") else f"{category}/{path}"
    return f"{key}:{entry}" if entry else key


def env_sort_key(name: str) -> tuple[str, str]:
    """Sort names case-insensitively, then by exact case so the order is stable."""
    return (name.casefold(), name)


def sorted_env(env: Mapping[str, str]) -> list[tuple[str, str]]:
    """Environment variables as (name, value) pairs, alphabetised by name."""
    return sorted(env.items(), key=lambda item: env_sort_key(item[0]))


def env_name_problem(name: str) -> str | None:
    """Why `name` can't be an environment variable name, or None if it can.

    setenv itself only refuses an empty name, "=" and NUL, but names with
    spaces or punctuation can't be used from a shell or by most tools, so
    names must be POSIX's portable ones: ASCII letters, digits and
    underscores, not starting with a digit.
    """
    if not name:
        return "Enter a name for the variable."
    if ENV_NAME.fullmatch(name) is None:
        if name[0].isdigit():
            return "A variable name can't start with a digit."
        return "A variable name can only use letters, digits and _ (no spaces)."
    return None


def env_value_problem(value: str) -> str | None:
    """Why `value` can't be an environment variable's value, or None if it can."""
    if "\0" in value:
        return "A value can't contain a NUL character."
    return None


def usable_env(env: Mapping[Any, Any]) -> dict[str, str]:
    """The variables in `env` that can be set, as strings; others are dropped.

    For tables read from launcher.toml, which may have been edited by hand.
    """
    pairs = ((str(k), str(v)) for k, v in env.items())
    return {
        k: v
        for k, v in pairs
        if env_name_problem(k) is None and env_value_problem(v) is None
    }


@dataclass(frozen=True)
class Layer:
    """One inherited layer of environment variables, named for the user."""

    source: str
    env: Mapping[str, str]


@dataclass(frozen=True)
class EnvRow:
    """A variable in effect at a layer: its own, or inherited from `source`."""

    name: str
    value: str
    source: str | None = None

    @property
    def inherited(self) -> bool:
        """Whether the value comes from an outer layer rather than this one."""
        return self.source is not None


def effective_rows(inherited: Sequence[Layer], own: Mapping[str, str]) -> list[EnvRow]:
    """The variables in effect at a layer, alphabetised.

    Inner layers override outer ones, and this layer's own values override all
    of them. Rows from outer layers name the layer they came from.
    """
    rows: dict[str, EnvRow] = {}
    for layer in inherited:
        for name, value in layer.env.items():
            rows[name] = EnvRow(name, value, layer.source)
    for name, value in own.items():
        rows[name] = EnvRow(name, value)
    return [rows[name] for name in sorted(rows, key=env_sort_key)]


def merged_env(layers: Iterable[Mapping[str, str]]) -> dict[str, str]:
    """Merge layers outermost first, so inner values win."""
    merged: dict[str, str] = {}
    for layer in layers:
        merged.update(layer)
    return merged


def can_move(length: int, index: int | None, where: Move) -> bool:
    """Whether the item at `index` can move `where` in a list of `length`."""
    if index is None or not 0 <= index < length:
        return False
    if where in ("top", "up"):
        return index > 0
    return index < length - 1


def move(items: list[str], index: int, where: Move) -> int:
    """Move ``items[index]`` in place, returning its new index."""
    if not can_move(len(items), index, where):
        return index
    item = items.pop(index)
    new_index = {
        "top": 0,
        "up": index - 1,
        "down": index + 1,
        "bottom": len(items),
    }[where]
    items.insert(new_index, item)
    return new_index
