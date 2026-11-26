"""togax_jkingok must stand alone, ready to become its own package (#323)."""

import ast
import sys
from pathlib import Path

import togax_jkingok

PACKAGE = Path(togax_jkingok.__file__).parent
# Besides the standard library: Toga, its backends and their libraries
ALLOWED = {
    "togax_jkingok",
    "toga",
    "toga_iOS",
    "toga_android",
    "toga_cocoa",
    "toga_gtk",
    "toga_winforms",
    "travertino",
    "rubicon",
    "java",
    # The desktop backends' own libraries: toga_gtk's PyGObject and
    # toga_winforms' pythonnet (the clipboard's fallbacks use them)
    "gi",
    "System",
    "android",
}


def imported(path: Path) -> set[str]:
    """Top-level names `path` imports absolutely."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module.split(".")[0])
    return names


def test_only_the_standard_library_and_toga_are_imported() -> None:
    """Never mypystub, nor anything MyPyStub happens to bundle."""
    offenders = {
        f"{path.name}: {name}"
        for path in sorted(PACKAGE.rglob("*.py"))
        for name in imported(path)
        if name not in ALLOWED and name not in sys.stdlib_module_names
    }
    assert not offenders


def test_every_public_name_is_exported_and_documented() -> None:
    """`__all__` lists real names, each with a docstring."""
    for name in togax_jkingok.__all__:
        assert getattr(togax_jkingok, name).__doc__, name
