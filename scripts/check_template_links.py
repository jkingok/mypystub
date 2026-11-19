"""Stop a build early if the project template's symbolic links are broken.

The template (``src/mypystub/resources/templates/project``) shares files with
the launcher as symbolic links. A clone without link support (Windows, unless
``core.symlinks`` was on before cloning) has one-line text files in their
place, and an app built from it would carry a damaged template. Fastlane's
lanes and ``scripts/build_android.py`` run this first, so such a build fails
before anything is made.

    python scripts/check_template_links.py

Exits 0 when the template is whole, 1 (listing the files) when it isn't. It
needs only the standard library.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "mypystub" / "resources" / "templates" / "project"
MODULE = ROOT / "src" / "mypystub" / "template_links.py"


def load_checker():
    """``mypystub.template_links``, loaded on its own (no package imports)."""
    spec = importlib.util.spec_from_file_location("template_links", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(template: Path = TEMPLATE) -> int:
    """Report the template's broken links; 0 if there are none."""
    found = load_checker().problems(template)
    if not found:
        return 0
    print("The project template's symbolic links are broken:", file=sys.stderr)
    for problem in found:
        print(f"  {problem}", file=sys.stderr)
    print(
        "This clone was made without symbolic links. On Windows, turn on "
        "Developer Mode and `git config --global core.symlinks true`, then "
        "clone again (or `git checkout -- src/mypystub/resources/templates`).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
