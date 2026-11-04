"""Objective-C classes come from toga_iOS.libs, or from bridge.py (#78).

Defining a class with rubicon's ObjCClass in several places can clash with the
copy toga_iOS already set up ("multiple implementation" errors), and
load_library should only open frameworks that Toga hasn't already loaded.

Examples can't import bridge.py, so like it they may use these for what toga_iOS
doesn't provide. That can't be checked here: desktop and CI have no toga_iOS.
"""

import re
from pathlib import Path

import mypystub

SRC = Path(mypystub.__file__).parent
BRIDGE = SRC / "bridge.py"
EXAMPLES = SRC / "resources" / "examples"
DIRECT = re.compile(r"\b(ObjCClass|load_library)\s*\(")


def test_objc_classes_are_only_created_in_bridge() -> None:
    """No ObjCClass(...) or load_library(...) calls in the app outside bridge.py."""
    offenders = [
        f"{path.relative_to(SRC)}:{number}"
        for path in sorted(SRC.rglob("*.py"))
        if path != BRIDGE and not path.is_relative_to(EXAMPLES)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if DIRECT.search(line) and not line.lstrip().startswith("#")
    ]
    assert not offenders, (
        f"import from toga_iOS.libs, or add the class to bridge.py: {offenders}"
    )


def test_bridge_is_importable_off_ios() -> None:
    """bridge.py only touches rubicon on iOS, so desktop and CI can import it."""
    from mypystub import bridge

    assert bridge.__doc__
