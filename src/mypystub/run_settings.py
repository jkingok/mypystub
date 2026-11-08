"""Saved per-thing Setup settings: command-line arguments and environment variables.

Environment variables are inherited in layers, each overriding the one before:
the system (the process environment), then Setup, then the package, then the
entry point or script. Arguments belong to one runnable thing and are not
inherited.

A variable's value is a string, or ``None`` for *unset*: the variable is removed
for the run. A layer can unset what an outer layer set, and an inner layer can
set it again. In ``launcher.toml`` the unset names are an ``unset`` list beside
the ``env`` table, so a variable can still be called anything.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Any, Literal

ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# A variable's value in a layer: text, or None to unset it
EnvValue = str | None
# The layer the process environment forms, shown as "from the system"
SYSTEM = "the system"

Move = Literal["top", "up", "down", "bottom"]
MOVES: tuple[Move, ...] = ("top", "up", "down", "bottom")


@dataclass
class RunSettings:
    """The arguments and environment variables saved for one thing."""

    args: list[str] = field(default_factory=list)
    env: dict[str, EnvValue] = field(default_factory=dict)

    @classmethod
    def from_table(cls, table: Mapping[str, Any] | None) -> RunSettings:
        """Read settings from a TOML table, ignoring anything malformed."""
        table = table or {}
        args = table.get("args", [])
        env = table.get("env", {})
        return cls(
            args=[str(a) for a in args] if isinstance(args, list) else [],
            env=with_unset(
                usable_env(env) if isinstance(env, Mapping) else {},
                table.get("unset", []),
            ),
        )

    def to_table(self, *, with_args: bool = True) -> dict[str, Any]:
        """The settings as a TOML table; `with_args` False saves the environment only."""
        table: dict[str, Any] = {}
        if with_args:
            table["args"] = list(self.args)
        values, unset = split_env(self.env)
        table["env"] = dict(sorted_env(values))
        if unset:
            table["unset"] = unset
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


def parse_settings_key(key: str) -> tuple[str, PurePath, str | None] | None:
    """Split a settings key back into ``(category, relative, entry)``.

    The inverse of :func:`settings_key`. ``entry`` is an entry point's name
    when the key carries a trailing ``:entry``, else None. Returns None for an
    empty key or one with no category. (A path cannot itself contain ``:``,
    which the Files app disallows in names.)
    """
    if not key:
        return None
    body, sep, entry = key.rpartition(":")
    if not sep:
        body, entry = key, ""
    category, _, path = body.partition("/")
    if not category:
        return None
    return category, PurePath(path) if path else PurePath(), entry or None


def quick_start_name(key: str) -> str:
    """A short human label for a settings key, for prompts and messages."""
    parsed = parse_settings_key(key)
    if parsed is None:
        return key
    category, relative, entry = parsed
    base = relative.as_posix() if relative != PurePath() else category
    return f"{base} · {entry}" if entry else base


def env_sort_key(name: str) -> tuple[str, str]:
    """Sort names case-insensitively, then by exact case so the order is stable."""
    return (name.casefold(), name)


def sorted_env(env: Mapping[str, EnvValue]) -> list[tuple[str, EnvValue]]:
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


def with_unset(env: Mapping[str, str], unset: Any) -> dict[str, EnvValue]:
    """`env` plus the names in `unset` as unset (None); bad names are dropped.

    A name both set and unset in a hand-edited file counts as unset: that is the
    explicit one.
    """
    result: dict[str, EnvValue] = dict(env)
    if isinstance(unset, list):
        for name in unset:
            if isinstance(name, str) and env_name_problem(name) is None:
                result[name] = None
    return result


def split_env(env: Mapping[str, EnvValue]) -> tuple[dict[str, str], list[str]]:
    """Separate set variables from the names of unset ones (sorted)."""
    values = {name: value for name, value in env.items() if value is not None}
    unset = sorted((n for n, v in env.items() if v is None), key=env_sort_key)
    return values, unset


@dataclass(frozen=True)
class Layer:
    """One inherited layer of environment variables, named for the user."""

    source: str
    env: Mapping[str, EnvValue]


@dataclass(frozen=True)
class EnvRow:
    """A variable in effect at a layer: its own, or inherited from `source`.

    `unset` rows have no value: the variable is removed for the run.
    """

    name: str
    value: str
    source: str | None = None
    unset: bool = False

    @property
    def inherited(self) -> bool:
        """Whether the value comes from an outer layer rather than this one."""
        return self.source is not None


def effective_rows(
    inherited: Sequence[Layer], own: Mapping[str, EnvValue]
) -> list[EnvRow]:
    """The variables in effect at a layer, alphabetised.

    Inner layers override outer ones, and this layer's own values override all
    of them. Rows from outer layers name the layer they came from.
    """
    rows: dict[str, EnvRow] = {}
    for layer in inherited:
        for name, value in layer.env.items():
            rows[name] = EnvRow(name, value or "", layer.source, value is None)
    for name, value in own.items():
        rows[name] = EnvRow(name, value or "", None, value is None)
    return [rows[name] for name in sorted(rows, key=env_sort_key)]


def merged_env(layers: Iterable[Mapping[str, EnvValue]]) -> dict[str, EnvValue]:
    """Merge layers outermost first, so inner values win; None stays "unset"."""
    merged: dict[str, EnvValue] = {}
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
