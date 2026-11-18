"""Only pure Python is installed at run time (#172).

iOS can't load code that wasn't signed into the app, and there is no compiler
or ``subprocess`` to build anything with. So a wheel that declares itself
impure is refused on every pathway, including one built from source here
(#257, where a build that needs a compiler fails before that); compiled
packages have to be bundled in the app instead.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

# Files that are compiled code, or only exist to build it
COMPILED_SUFFIXES = (".so", ".dylib", ".pyd", ".dll", ".a", ".o", ".framework")


def wheel_impurity(path: Path) -> str | None:
    """Why the wheel at `path` isn't pure Python, or None if it is.

    Looks at what the wheel says about itself (its tags and ``Root-Is-Purelib``)
    and at what it holds, since a wheel can be tagged ``any`` and still carry a
    binary.
    """
    from packaging.utils import InvalidWheelFilename, parse_wheel_filename

    try:
        _, _, _, tags = parse_wheel_filename(path.name)
    except InvalidWheelFilename:
        tags = frozenset()
    for tag in tags:
        if tag.platform != "any" or tag.abi != "none":
            return f"it is built for {tag} (not pure Python)"
    try:
        with zipfile.ZipFile(path) as wheel:
            names = wheel.namelist()
            for name in names:
                if name.endswith(".dist-info/WHEEL"):
                    text = wheel.read(name).decode("utf-8", "replace")
                    if re.search(
                        r"^Root-Is-Purelib:\s*false\s*$",
                        text,
                        re.IGNORECASE | re.MULTILINE,
                    ):
                        return "it says Root-Is-Purelib: false"
    except zipfile.BadZipFile:
        return None  # a bad archive is reported where it is unpacked
    for name in names:
        lowered = name.lower().rstrip("/")
        if lowered.endswith(COMPILED_SUFFIXES) or ".framework/" in lowered:
            return f"it contains compiled code ({name})"
    return None
