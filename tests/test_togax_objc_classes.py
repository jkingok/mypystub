"""Objective-C classes in togax_jkingok: private iOS modules only, each once.

The same rule as the launcher's (tests/test_objc_usage.py): an ObjCClass for
a class toga_iOS already set up can clash with its copy, and two lookups of
one class in different places invite that. The package keeps its own in
private ``_ios_*`` and ``_cocoa_*`` modules, and the launcher's bridge.py doesn't repeat them.
"""

from __future__ import annotations

import re
from pathlib import Path

import mypystub
import togax_jkingok

PACKAGE = Path(togax_jkingok.__file__).parent
BRIDGE = Path(mypystub.__file__).parent / "bridge.py"
LOOKUP = re.compile(r"\bObjCClass\(\s*\"(\w+)\"\s*\)")


def lookups(path: Path) -> set[str]:
    return set(LOOKUP.findall(path.read_text(encoding="utf-8")))


def test_only_private_ios_modules_look_classes_up() -> None:
    offenders = [
        p.name
        for p in PACKAGE.glob("*.py")
        if lookups(p) and not p.name.startswith(("_ios_", "_cocoa_"))
    ]
    assert not offenders


def test_no_class_is_looked_up_in_two_places() -> None:
    package = [name for p in PACKAGE.glob("*.py") for name in lookups(p)]
    assert len(package) == len(set(package))
    assert not set(package) & lookups(BRIDGE)
    assert "UIPasteboard" in package  # the clipboard's, now
