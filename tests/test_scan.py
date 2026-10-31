"""Tests for prototype discovery in mypystub.piplike."""

import os
from pathlib import Path

import pytest

from mypystub import piplike


def write(path: Path, text: str = "") -> Path:
    """Create `path` with `text`, making parent folders as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def script_with_metadata(body: str) -> str:
    """Wrap TOML lines in a PEP 723 `script` block."""
    lines = "".join(f"# {line}\n" for line in body.strip().splitlines())
    return f"# /// script\n{lines}# ///\nprint('hi')\n"


def titles(base: Path) -> list[str]:
    """Titles of the entries scanned from `base`, in order."""
    return [entry["title"] for entry in piplike.scan_all_prototypes(base)]


def test_missing_base_dir_is_empty(tmp_path: Path) -> None:
    """A category folder that does not exist yet lists nothing."""
    assert list(piplike.scan_all_prototypes(tmp_path / "nope")) == []


def test_lists_scripts_and_skips_reserved_and_hidden(tmp_path: Path) -> None:
    """Loose scripts are listed; launcher files, hidden files and non-.py are not."""
    write(tmp_path / "b_script.py")
    write(tmp_path / "A_script.py")
    write(tmp_path / "patch_app.py")
    write(tmp_path / "__init__.py")
    write(tmp_path / ".hidden.py")
    write(tmp_path / "notes.txt")
    assert titles(tmp_path) == ["A_script", "b_script"]


def test_script_dependencies_from_pep723(tmp_path: Path) -> None:
    """Dependencies in the PEP 723 block are passed through."""
    write(
        tmp_path / "deps.py",
        script_with_metadata('dependencies = ["requests", "rich>=13"]'),
    )
    (entry,) = piplike.scan_all_prototypes(tmp_path)
    assert entry["dependencies"] == ["requests", "rich>=13"]
    assert entry["entry_point"] == tmp_path / "deps.py"
    assert entry["folder_root"] == tmp_path


def test_script_with_incompatible_requires_python_is_skipped(tmp_path: Path) -> None:
    """A script that cannot run on this Python is not listed (#38)."""
    write(
        tmp_path / "old.py",
        script_with_metadata('requires-python = "<3.0"\ndependencies = ["x"]'),
    )
    write(tmp_path / "ok.py", script_with_metadata('requires-python = ">=3.8"'))
    assert titles(tmp_path) == ["ok"]


def test_non_script_metadata_blocks_are_ignored(tmp_path: Path) -> None:
    """Only the `script` block type is read."""
    write(tmp_path / "other.py", "# /// other\n# dependencies = ['x']\n# ///\n")
    (entry,) = piplike.scan_all_prototypes(tmp_path)
    assert entry["dependencies"] == []


def test_project_folder_reads_pyproject(tmp_path: Path) -> None:
    """A folder with pyproject.toml is a single runnable project entry."""
    write(
        tmp_path / "proj" / "pyproject.toml",
        """
[project]
name = "proj"
description = "A project"
dependencies = ["anyio"]

[tool.stub_launcher]
display_name = "My Project"
entry_point = "src/proj/__main__.py"
icon = "icon.png"
""",
    )
    (entry,) = piplike.scan_all_prototypes(tmp_path)
    assert entry["title"] == "My Project"
    assert entry["subtitle"] == "A project"
    assert entry["dependencies"] == ["anyio"]
    assert entry["entry_point"] == tmp_path / "proj" / "src/proj/__main__.py"
    assert entry["folder_root"] == tmp_path / "proj" / "src"
    assert entry["icon_path"] == tmp_path / "proj" / "icon.png"
    assert "folder" not in entry


def test_plain_folders_are_navigable_and_listed_first(tmp_path: Path) -> None:
    """Folders without pyproject.toml become folder entries ahead of scripts (#35)."""
    write(tmp_path / "a_script.py")
    write(tmp_path / "zoo" / "inner.py")
    write(tmp_path / "__pycache__" / "x.pyc")
    write(tmp_path / ".git" / "HEAD")
    entries = list(piplike.scan_all_prototypes(tmp_path))
    assert [e["title"] for e in entries] == ["zoo", "a_script"]
    assert entries[0]["folder"] == tmp_path / "zoo"
    assert "entry_point" not in entries[0]


def test_nested_folders_can_be_walked(tmp_path: Path) -> None:
    """Scripts several levels down are reachable by following folder entries."""
    write(tmp_path / "a" / "b" / "deep.py")
    path = tmp_path
    for expected in ["a", "b"]:
        (entry,) = piplike.scan_all_prototypes(path)
        assert entry["title"] == expected
        path = entry["folder"]
    assert titles(path) == ["deep"]


def test_malformed_entries_are_skipped(tmp_path: Path) -> None:
    """Broken TOML in a project or script does not break the whole list."""
    write(tmp_path / "bad_proj" / "pyproject.toml", "[project\n")
    write(tmp_path / "bad_script.py", "# /// script\n# = = =\n# ///\n")
    write(
        tmp_path / "bad_spec.py",
        script_with_metadata('requires-python = "not a spec"'),
    )
    write(tmp_path / "good.py")
    assert titles(tmp_path) == ["good"]


def test_relative_folder_stays_inside_base(tmp_path: Path) -> None:
    """Navigation paths are relative and cannot climb out of the base folder."""
    (tmp_path / "base" / "a" / "b").mkdir(parents=True)
    base = tmp_path / "base"
    assert piplike.relative_folder(base, base / "a" / "b") == Path("a/b")
    assert piplike.relative_folder(base, base / "a" / "b" / "..") == Path("a")
    assert piplike.relative_folder(base, base) == Path()
    assert piplike.relative_folder(base, tmp_path) == Path()


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
def test_relative_folder_rejects_symlink_escape(tmp_path: Path) -> None:
    """A symlink pointing outside the base resolves back to the base."""
    base = tmp_path / "base"
    base.mkdir()
    (tmp_path / "outside").mkdir()
    (base / "link").symlink_to(tmp_path / "outside")
    assert piplike.relative_folder(base, base / "link") == Path()


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('"""Draw a spinning cube."""\n', "Draw a spinning cube."),
        (
            '#!/usr/bin/env python\n"""\n  Fetch the weather.\n\n  Longer text.\n"""\n',
            "Fetch the weather.",
        ),
        ("# just a comment\nprint('hi')\n", piplike.DEFAULT_SCRIPT_SUBTITLE),
        ('x = 1\n"""Not a module docstring."""\n', piplike.DEFAULT_SCRIPT_SUBTITLE),
        ('""""""\n', piplike.DEFAULT_SCRIPT_SUBTITLE),
        ('"""Broken script."""\ndef oops(:\n', piplike.DEFAULT_SCRIPT_SUBTITLE),
    ],
    ids=["one-line", "multi-line", "none", "not-first", "empty", "syntax-error"],
)
def test_script_subtitle_from_docstring(
    tmp_path: Path, source: str, expected: str
) -> None:
    """The first line of the module docstring becomes the subtitle."""
    write(tmp_path / "s.py", source)
    (entry,) = piplike.scan_all_prototypes(tmp_path)
    assert entry["subtitle"] == expected


def test_docstring_after_pep723_block(tmp_path: Path) -> None:
    """PEP 723 metadata comments before the docstring do not hide it."""
    write(
        tmp_path / "s.py",
        script_with_metadata('dependencies = ["x"]').replace(
            "print('hi')", '"""Uses x."""'
        ),
    )
    (entry,) = piplike.scan_all_prototypes(tmp_path)
    assert entry["subtitle"] == "Uses x."
    assert entry["dependencies"] == ["x"]


def test_entries_report_their_kind(tmp_path: Path) -> None:
    """Each entry says whether it is a folder, project or loose script."""
    write(tmp_path / "folder" / "x.py")
    write(tmp_path / "proj" / "pyproject.toml", "[project]\nname = 'proj'\n")
    write(tmp_path / "script.py")
    kinds = {e["title"]: e["kind"] for e in piplike.scan_all_prototypes(tmp_path)}
    assert kinds == {"folder": "folder", "proj": "project", "script": "script"}
