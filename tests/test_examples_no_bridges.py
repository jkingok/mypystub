"""Every bundled example starts without the other platforms' bridges (#264).

- **Every file**, read without running it: anything that runs at import (the
  module body and class bodies, not function bodies) may only import Rubicon,
  ``toga_iOS``, Chaquopy (``java``, ``com.chaquo``) or ``toga_android``, or load
  a system framework with ctypes, inside an ``if`` on ``sys.platform``. And the
  deprecated ``toga.platform.current_platform`` isn't used. Many examples run
  at the top (they're scripts), so reading is the only safe check for them.
- **Every project's package modules**, imported (they only define things)
  three times: as on a desktop with no Rubicon, ``toga_iOS``, Chaquopy or
  ``toga_android``; as on iOS with Chaquopy missing; and as on Android with
  Rubicon missing.
"""

import ast
import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).parent.parent / "src" / "mypystub" / "resources" / "examples"
APPLE = ["rubicon", "rubicon.objc", "toga_iOS", "toga_iOS.libs"]
CHAQUOPY = ["java", "com", "com.chaquo", "com.chaquo.python", "toga_android"]
PLATFORMS = {"linux": APPLE + CHAQUOPY, "ios": CHAQUOPY, "android": APPLE}


def projects() -> list[Path]:
    """Each example project's folder (it has a pyproject.toml)."""
    return sorted(p.parent for p in EXAMPLES.rglob("pyproject.toml"))


def project_modules(project: Path) -> list[str]:
    """Dotted names of a project's package modules, under its src/."""
    src = project / "src"
    return sorted(
        ".".join(p.relative_to(src).with_suffix("").parts)
        for p in src.rglob("*.py")
        if "__pycache__" not in p.parts and p.name != "__main__.py"
    )


def label(path: Path) -> str:
    return str(path.relative_to(EXAMPLES))


BRIDGES = ("rubicon", "toga_iOS", "java", "com.chaquo", "toga_android")


def every_file() -> list[Path]:
    """Every example source file."""
    return sorted(p for p in EXAMPLES.rglob("*.py") if "__pycache__" not in p.parts)


def is_bridge(module: str | None) -> bool:
    return bool(module) and any(
        module == b or module.startswith(f"{b}.")  # type: ignore[union-attr]
        for b in BRIDGES
    )


def decides_on_platform(node: ast.If) -> bool:
    """Whether an ``if`` decides on ``sys.platform``."""
    return any(
        isinstance(n, ast.Attribute)
        and n.attr == "platform"
        and isinstance(n.value, ast.Name)
        and n.value.id == "sys"
        for n in ast.walk(node.test)
    )


def unguarded(body: list[ast.stmt]) -> list[ast.AST]:
    """What runs at import, outside a platform check, that needs a bridge."""
    found: list[ast.AST] = []
    for node in body:
        if isinstance(node, ast.If) and decides_on_platform(node):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(node, ast.Import):
            found += [node for alias in node.names if is_bridge(alias.name)]
            continue
        if isinstance(node, ast.ImportFrom) and is_bridge(node.module):
            found.append(node)
            continue
        if isinstance(node, ast.ClassDef):
            found += unguarded(node.body)
            continue
        # Nested blocks (if, try, with, for) still run at import
        for field in ("body", "orelse", "finalbody", "handlers"):
            inner = getattr(node, field, None)
            if isinstance(inner, list):
                found += unguarded([n for n in inner if isinstance(n, ast.stmt)])
                for handler in inner:
                    if isinstance(handler, ast.ExceptHandler):
                        found += unguarded(handler.body)
        found += [
            call
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
            and any(
                isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
                and arg.value.startswith("/System/Library/")
                for arg in call.args
            )
        ]
    return found


@pytest.mark.parametrize("path", every_file(), ids=label)
def test_platform_code_is_behind_a_platform_check(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = [getattr(node, "lineno", 0) for node in unguarded(tree.body)]
    assert not lines, f"{label(path)}: platform-only code at import, lines {lines}"


@pytest.mark.parametrize("path", every_file(), ids=label)
def test_the_platform_comes_from_sys(path: Path) -> None:
    """toga.platform.current_platform is deprecated: use sys.platform."""
    assert "current_platform" not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("platform", PLATFORMS)
@pytest.mark.parametrize("project", projects(), ids=label)
def test_a_project_imports(project: Path, platform: str) -> None:
    names = project_modules(project)
    packages = {name.split(".")[0] for name in names}
    saved_platform, saved_path = sys.platform, list(sys.path)
    blocked = {name: sys.modules.get(name) for name in PLATFORMS[platform]}
    problem = ""
    try:
        sys.platform = platform  # type: ignore[misc]
        sys.path.insert(0, str(project / "src"))
        for name in blocked:
            sys.modules[name] = None  # type: ignore[assignment]
        for name in names:
            try:
                importlib.import_module(name)
            except ModuleNotFoundError as error:
                root = (error.name or "").split(".")[0]
                if root in blocked or (error.name or "") in blocked:
                    problem = f"{name}: {error}"
                    break
                # A dependency this test environment doesn't have (humanize, or
                # Rubicon itself when pretending to be iOS): not what's tested
            except Exception as error:  # noqa: BLE001  (reported below)
                problem = f"{name}: {type(error).__name__}: {error}"
                break
    finally:
        sys.platform = saved_platform  # type: ignore[misc]
        sys.path[:] = saved_path
        for name, module in blocked.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        for name in [n for n in sys.modules if n.split(".")[0] in packages]:
            del sys.modules[name]
    assert not problem, f"as on {platform}, {problem}"
