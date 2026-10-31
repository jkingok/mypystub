"""Checks that the sample prototypes are bundled where the Examples category looks."""

import ast
import sys
from pathlib import Path

import pytest

import mypystub
from mypystub import piplike

# Same folder as Prototype.get_category_dir() uses for "Examples"
BUNDLED = Path(mypystub.__file__).parent / "resources" / "examples"
REPO_EXAMPLES = Path(__file__).parent.parent / "examples"


def walk(folder: Path) -> dict[str, list[str]]:
    """Follow folder entries like the launcher does; map folder to its titles."""
    found: dict[str, list[str]] = {}
    entries = list(piplike.scan_all_prototypes(folder))
    found[folder.relative_to(BUNDLED).as_posix()] = [e["title"] for e in entries]
    for entry in entries:
        if "folder" in entry:
            found |= walk(entry["folder"])
    return found


def test_examples_are_grouped_in_folders() -> None:
    """The top level shows only folders, and every sample is reachable."""
    tree = walk(BUNDLED)
    assert tree["."] == ["basics", "errors", "maintenance", "threads"]
    assert tree["basics"] == ["hello_world", "hello_you"]
    assert tree["errors"] == ["main_thread_error", "test_error"]
    assert tree["threads"] == ["main_thread"]
    assert tree["maintenance"] == ["wipe_site_packages_from_cache"]


def test_example_folders_do_not_shadow_modules() -> None:
    """Scripts run as a module named after their folder, so avoid real names."""
    folders = [p.name for p in BUNDLED.iterdir() if p.is_dir()]
    clashes = [name for name in folders if name in sys.stdlib_module_names]
    assert not clashes, f"rename example folders: {clashes}"


@pytest.mark.skipif(
    not REPO_EXAMPLES.exists(), reason="repo checkout only, not on device"
)
def test_repo_examples_folder_is_the_bundled_folder() -> None:
    """examples/ at the repo root must not drift from what the app ships."""
    assert REPO_EXAMPLES.is_symlink()
    assert REPO_EXAMPLES.resolve() == BUNDLED.resolve()


def test_every_example_has_a_docstring() -> None:
    """The list shows each example's docstring, so every example needs one."""
    missing = [
        path.name
        for path in sorted(BUNDLED.rglob("*.py"))
        if not ast.get_docstring(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert not missing, f"add a one-line module docstring to: {missing}"
