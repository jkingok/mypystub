"""Prototypes must run unchanged as standalone apps (see CLAUDE.md)."""

import ast
from pathlib import Path

import mypystub

EXAMPLES = Path(mypystub.__file__).parent / "resources" / "examples"


def imported_modules(source: str) -> set[str]:
    """Top-level package names imported anywhere in `source`."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module.split(".")[0])
    return names


def test_no_example_imports_mypystub() -> None:
    """Examples use standard Python, Toga or Rubicon, never the launcher."""
    offenders = [
        str(path.relative_to(EXAMPLES))
        for path in sorted(EXAMPLES.rglob("*.py"))
        if "mypystub" in imported_modules(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"examples must not import mypystub: {offenders}"


def test_detects_mypystub_imports() -> None:
    """The check catches both import styles, and ignores relative imports."""
    assert "mypystub" in imported_modules("import mypystub.ui\n")
    assert "mypystub" in imported_modules("from mypystub import piplike\n")
    assert "mypystub" not in imported_modules("from .mypystub import x\n")
