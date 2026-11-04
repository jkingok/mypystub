"""Checks that the sample prototypes are bundled where the Examples category looks."""

import ast
import sys
from pathlib import Path

import pytest

import mypystub
from mypystub import scan

# Same folder as Prototype.get_category_dir() uses for "Examples"
BUNDLED = Path(mypystub.__file__).parent / "resources" / "examples"
REPO_EXAMPLES = Path(__file__).parent.parent / "examples"

# Core examples: the folders and files the launcher's own tests rely on. These
# get every check. Anything else in the bundled folder is an extra example that
# can be added or removed freely: it must not break the launcher, but it isn't
# held to the core rules (folder layout, docstrings, main() guards, bridge use).
CORE_FOLDERS = frozenset({"basics", "errors", "hardware", "takeover", "threads"})
CORE_FILES = frozenset(
    {
        "basics/hello_world.py",
        "basics/hello_you.py",
        "basics/args_and_env.py",
        "basics/show_args.py",
        "basics/show_env.py",
        "basics/with_dependency.py",
        "basics/repl.py",
        "basics/console.py",
        "threads/countdown.py",
        "threads/main_thread.py",
        "takeover/back_button.py",
        "takeover/nested_takeover.py",
        "errors/main_thread_error.py",
        "errors/test_error.py",
    }
)


def core_files() -> list[Path]:
    """The core example scripts, in the bundled folder."""
    return [BUNDLED / name for name in sorted(CORE_FILES)]


def walk(folder: Path) -> dict[str, list[str]]:
    """Follow folder entries like the launcher does; map folder to its titles."""
    found: dict[str, list[str]] = {}
    entries = list(scan.scan_all_prototypes(folder))
    found[folder.relative_to(BUNDLED).as_posix()] = [e["title"] for e in entries]
    for entry in entries:
        if "folder" in entry:
            found |= walk(entry["folder"])
    return found


def test_examples_are_grouped_in_folders() -> None:
    """The core folders are reachable; extra folders may come and go."""
    tree = walk(BUNDLED)
    assert CORE_FOLDERS <= set(tree["."])
    # Each core folder lists its core samples; extras may also be there
    core_titles = {
        "basics": {
            "args_and_env",
            "console",
            "hello_world",
            "hello_you",
            "repl",
            "show_args",
            "show_env",
            "with_dependency",
        },
        "hardware": {"paste_diagnostics", "router_check", "take_photo", "where_am_i"},
        "errors": {"main_thread_error", "test_error"},
        "threads": {"countdown", "main_thread"},
        "takeover": {"back_button", "nested_takeover"},
    }
    for folder, titles in core_titles.items():
        assert titles <= set(tree[folder]), folder


def test_project_example_is_one_runnable_entry() -> None:
    """The project folder shows as a single project, not a folder to open."""
    entries = scan.scan_all_prototypes(BUNDLED / "basics")
    (project,) = [e for e in entries if e["kind"] == "project"]
    assert project["title"] == "Hello Project"
    assert project["dependencies"] == ["humanize"]
    assert project["entry_point"].is_file()
    assert (project["folder_root"] / "hello_project" / "__init__.py").is_file()


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


def test_every_core_example_has_a_docstring() -> None:
    """The list shows each core example's docstring, so each needs one."""
    missing = [
        path.name
        for path in core_files()
        if not ast.get_docstring(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert not missing, f"add a one-line module docstring to: {missing}"


def is_main_guard(node: ast.stmt) -> bool:
    """Whether `node` is an `if __name__ == "__main__":` block."""
    return (
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
    )


def test_examples_that_define_main_call_it() -> None:
    """Scripts run as __main__, like `python script.py` (#75).

    The launcher doesn't call main() for you, so an example that defines main()
    must also call it under `if __name__ == "__main__":`, or it does nothing.
    """
    silent = []
    for path in core_files():
        body = ast.parse(path.read_text(encoding="utf-8")).body
        has_main = any(
            isinstance(node, ast.FunctionDef) and node.name == "main" for node in body
        )
        if has_main and not any(is_main_guard(node) for node in body):
            silent.append(path.name)
    assert not silent, f"call main() under a __name__ guard: {silent}"
