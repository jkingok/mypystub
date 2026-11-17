"""Titles from an item's metadata, with the file name as the fallback (#235)."""

import zipfile
from pathlib import Path

import pytest

from mypystub import scan
from mypystub.titles import clean_title, distinguishing_parts


def titles(folder: Path) -> list[str]:
    return [str(r["title"]) for r in scan.scan_all_prototypes(folder)]


def project(folder: Path, name: str, extra: str = "") -> Path:
    path = folder / name
    path.mkdir()
    (path / "pyproject.toml").write_text(
        f'[project]\nname = "{name}-id"\nversion = "1"\n{extra}'
    )
    (path / "main.py").write_text("print(1)\n")
    return path


def test_clean_title() -> None:
    assert clean_title("  A\n  title\t ") == "A title"
    assert (
        clean_title("") is None and clean_title(None) is None and clean_title(3) is None
    )
    assert clean_title("x" * 100) == "x" * 100  # no cap: the row shortens it


def test_project_prefers_display_name_then_formal_name_then_name(
    tmp_path: Path,
) -> None:
    project(tmp_path, "a", '[tool.stub_launcher]\ndisplay_name = "Shown"\n')
    project(
        tmp_path,
        "b",
        '[tool.briefcase.app.b]\nformal_name = "Formal B"\n',
    )
    project(tmp_path, "c")
    assert sorted(titles(tmp_path)) == sorted(["Shown", "Formal B", "c-id"])


def test_zipapp_uses_its_metadata_name(tmp_path: Path) -> None:
    with zipfile.ZipFile(tmp_path / "tool.pyz", "w") as z:
        z.writestr("__main__.py", "print(1)")
        z.writestr("tool-1.dist-info/METADATA", "Name: Nice Tool\nVersion: 1\n")
    with zipfile.ZipFile(tmp_path / "bare.pyz", "w") as z:
        z.writestr("__main__.py", "print(1)")
    assert sorted(titles(tmp_path)) == ["Nice Tool", "bare"]


def test_script_keeps_its_display_name_or_file_name(tmp_path: Path) -> None:
    (tmp_path / "plain.py").write_text('"""A script."""\n')
    (tmp_path / "named.py").write_text(
        "# /// script\n# [tool.stub_launcher]\n# display_name = 'Named One'\n# ///\n"
    )
    assert sorted(titles(tmp_path)) == ["Named One", "plain"]


def test_duplicate_titles_get_what_tells_their_files_apart(tmp_path: Path) -> None:
    for name in ("app_v1", "app_v2"):
        project(tmp_path, name, '[tool.stub_launcher]\ndisplay_name = "App"\n')
    assert titles(tmp_path) == ["App (v1)", "App (v2)"]


def test_duplicate_scripts_drop_their_suffix(tmp_path: Path) -> None:
    for name in ("tool", "tool_old"):
        (tmp_path / f"{name}.py").write_text(
            "# /// script\n# [tool.stub_launcher]\n# display_name = 'Tool'\n# ///\n"
        )
    assert titles(tmp_path) == ["Tool (old)", "Tool (tool)"]


@pytest.mark.parametrize(
    ("names", "parts"),
    [
        (["app_v1", "app_v2"], ["v1", "v2"]),
        (["my-app-beta", "my-app-final"], ["beta", "final"]),
        (["old_tool_x", "new_tool_x"], ["old", "new"]),
        (["tool", "tool_old"], ["tool", "old"]),
        (["a", "b", "c"], ["a", "b", "c"]),
    ],
)
def test_distinguishing_parts(names: list[str], parts: list[str]) -> None:
    assert distinguishing_parts(names) == parts


def test_order_follows_the_title_shown(tmp_path: Path) -> None:
    project(tmp_path, "a", '[tool.stub_launcher]\ndisplay_name = "Zed"\n')
    project(tmp_path, "b", '[tool.stub_launcher]\ndisplay_name = "alpha"\n')
    assert titles(tmp_path) == ["alpha", "Zed"]
