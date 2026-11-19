"""Find the project template's symbolic links broken by a checkout without links.

The template shares some files with the launcher as relative symbolic links
(see new_items). Git on a system without link support (Windows, unless
``core.symlinks`` is on) checks each link out as a small one-line file holding
the target's path instead, and a link can also point at something missing.
:func:`problems` finds both. New refuses a damaged template with it, and
``scripts/check_template_links.py`` stops a build with it before it starts.

Standard library only, so the script can load this file on its own, with any
Python and before anything is installed.
"""

from __future__ import annotations

import re
from pathlib import Path

# A git checkout's stand-in for a symbolic link: one line, the target's path
LINK_STUB = re.compile(r"(\.\./)+[\w.\-/]+")
STUB_LIMIT = 512  # bytes: a stand-in is a short path, never a real file's size


def problems(root: Path) -> list[str]:
    """Files under `root` that should be a linked file's content but aren't.

    A link whose target is missing, or a short one-line file holding a relative
    path that ends in its own name. Each is named relative to `root`.
    """
    found = []
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        if path.is_symlink() and not path.exists():
            found.append(f"{name} (a link to something missing)")
        elif path.is_file() and path.stat().st_size < STUB_LIMIT:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if LINK_STUB.fullmatch(text) and text.endswith("/" + path.name):
                found.append(f"{name} (a link checked out as a text file)")
    return found
