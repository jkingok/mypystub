"""Requirements really satisfied by another distribution (#79).

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from packaging.utils import canonicalize_name

ALIAS_KINDS = ("bundled", "substitute")
ALIAS_WHEN = ("no_wheel", "always")
ALIAS_SPECIFIER = ("drop", "keep")


@dataclass(frozen=True)
class Alias:
    """A requirement that is really satisfied by another distribution (#79).

    :param kind: ``"bundled"``: satisfied by a distribution the app bundles, so
        nothing is installed (``toga`` is provided by ``toga-core``).
        ``"substitute"``: install `target` instead, typically a pure-Python
        replacement for a package with no wheel for this platform.
    :param target: The distribution that satisfies the requirement.
    :param when: For substitutes: ``"no_wheel"`` (the default) tries the
        original first and only substitutes when it has no compatible wheel;
        ``"always"`` always substitutes.
    :param specifier: For substitutes: ``"drop"`` (the default) ignores the
        requirement's version specifier, since the two projects number their
        versions differently; ``"keep"`` applies it to the substitute.
    """

    kind: str
    target: str
    when: str = "no_wheel"
    specifier: str = "drop"


# Built-in aliases. Each substitute is a verified drop-in: same import name,
# compatible API, and a pure-Python (py3-none-any) wheel.
ALIASES = {
    # The toga meta-package isn't bundled, but toga-core and the backend are
    "toga": Alias("bundled", "toga-core"),
    # PyYAML's wheels are compiled and none are built for iOS; pyyaml-pure
    # provides the same `yaml` package (safe_load, dump, YAMLError, loaders)
    "pyyaml": Alias("substitute", "pyyaml-pure"),
}


def parse_aliases(table: Mapping[str, Any]) -> dict[str, Alias]:
    """Read an alias table, as written in launcher.toml or [tool.stub_launcher].

    Each entry is ``name = { kind = "...", target = "...", when = "...",
    specifier = "..." }``. Raises ValueError for anything malformed, so typos
    don't silently change what gets installed.
    """
    aliases: dict[str, Alias] = {}
    for name, entry in table.items():
        if not isinstance(entry, Mapping) or "target" not in entry:
            raise ValueError(f"alias {name!r} needs a table with a target")
        alias = Alias(
            kind=str(entry.get("kind", "substitute")),
            target=canonicalize_name(str(entry["target"])),
            when=str(entry.get("when", "no_wheel")),
            specifier=str(entry.get("specifier", "drop")),
        )
        if (
            alias.kind not in ALIAS_KINDS
            or alias.when not in ALIAS_WHEN
            or alias.specifier not in ALIAS_SPECIFIER
        ):
            raise ValueError(f"alias {name!r} has an unknown kind, when or specifier")
        aliases[canonicalize_name(name)] = alias
    return aliases
