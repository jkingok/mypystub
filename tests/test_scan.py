"""Tests for prototype discovery in mypystub.piplike."""

import os
from pathlib import Path

import pytest

from mypystub import piplike, scan


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
    return [entry["title"] for entry in scan.scan_all_prototypes(base)]


def test_missing_base_dir_is_empty(tmp_path: Path) -> None:
    """A category folder that does not exist yet lists nothing."""
    assert list(scan.scan_all_prototypes(tmp_path / "nope")) == []


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
    (entry,) = scan.scan_all_prototypes(tmp_path)
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
    (entry,) = scan.scan_all_prototypes(tmp_path)
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
    (entry,) = scan.scan_all_prototypes(tmp_path)
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
    entries = list(scan.scan_all_prototypes(tmp_path))
    assert [e["title"] for e in entries] == ["zoo", "a_script"]
    assert entries[0]["folder"] == tmp_path / "zoo"
    assert "entry_point" not in entries[0]


def test_nested_folders_can_be_walked(tmp_path: Path) -> None:
    """Scripts several levels down are reachable by following folder entries."""
    write(tmp_path / "a" / "b" / "deep.py")
    path = tmp_path
    for expected in ["a", "b"]:
        (entry,) = scan.scan_all_prototypes(path)
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
    assert scan.relative_folder(base, base / "a" / "b") == Path("a/b")
    assert scan.relative_folder(base, base / "a" / "b" / "..") == Path("a")
    assert scan.relative_folder(base, base) == Path()
    assert scan.relative_folder(base, tmp_path) == Path()


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
def test_relative_folder_rejects_symlink_escape(tmp_path: Path) -> None:
    """A symlink pointing outside the base resolves back to the base."""
    base = tmp_path / "base"
    base.mkdir()
    (tmp_path / "outside").mkdir()
    (base / "link").symlink_to(tmp_path / "outside")
    assert scan.relative_folder(base, base / "link") == Path()


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('"""Draw a spinning cube."""\n', "Draw a spinning cube."),
        (
            '#!/usr/bin/env python\n"""\n  Fetch the weather.\n\n  Longer text.\n"""\n',
            "Fetch the weather.",
        ),
        ("# just a comment\nprint('hi')\n", scan.DEFAULT_SCRIPT_SUBTITLE),
        ('x = 1\n"""Not a module docstring."""\n', scan.DEFAULT_SCRIPT_SUBTITLE),
        ('""""""\n', scan.DEFAULT_SCRIPT_SUBTITLE),
        ('"""Broken script."""\ndef oops(:\n', scan.DEFAULT_SCRIPT_SUBTITLE),
    ],
    ids=["one-line", "multi-line", "none", "not-first", "empty", "syntax-error"],
)
def test_script_subtitle_from_docstring(
    tmp_path: Path, source: str, expected: str
) -> None:
    """The first line of the module docstring becomes the subtitle."""
    write(tmp_path / "s.py", source)
    (entry,) = scan.scan_all_prototypes(tmp_path)
    assert entry["subtitle"] == expected


def test_docstring_after_pep723_block(tmp_path: Path) -> None:
    """PEP 723 metadata comments before the docstring do not hide it."""
    write(
        tmp_path / "s.py",
        script_with_metadata('dependencies = ["x"]').replace(
            "print('hi')", '"""Uses x."""'
        ),
    )
    (entry,) = scan.scan_all_prototypes(tmp_path)
    assert entry["subtitle"] == "Uses x."
    assert entry["dependencies"] == ["x"]


def test_entries_report_their_kind(tmp_path: Path) -> None:
    """Each entry says whether it is a folder, project or loose script."""
    write(tmp_path / "folder" / "x.py")
    write(tmp_path / "proj" / "pyproject.toml", "[project]\nname = 'proj'\n")
    write(tmp_path / "script.py")
    kinds = {e["title"]: e["kind"] for e in scan.scan_all_prototypes(tmp_path)}
    assert kinds == {"folder": "folder", "proj": "project", "script": "script"}


def test_script_metadata_sets_title_description_and_icon(tmp_path: Path) -> None:
    """[tool.stub_launcher] in the PEP 723 block works like a project's (#52)."""
    write(tmp_path / "icons" / "globe.png", "png")
    write(
        tmp_path / "weather.py",
        script_with_metadata(
            'dependencies = ["httpx"]\n'
            "[tool.stub_launcher]\n"
            'display_name = "Weather Now"\n'
            'description = "Current conditions where you are."\n'
            'icon = "icons/globe.png"'
        ).replace("print('hi')", '"""Docstring loses to metadata."""'),
    )
    (entry,) = [e for e in scan.scan_all_prototypes(tmp_path) if e["kind"] == "script"]
    assert entry["title"] == "Weather Now"
    assert entry["subtitle"] == "Current conditions where you are."
    assert entry["icon_path"] == tmp_path / "icons" / "globe.png"
    assert entry["dependencies"] == ["httpx"]


def test_script_metadata_is_optional_per_key(tmp_path: Path) -> None:
    """Missing keys fall back: file stem, then docstring, then no icon."""
    write(
        tmp_path / "partial.py",
        script_with_metadata('[tool.stub_launcher]\ndisplay_name = "Partial"').replace(
            "print('hi')", '"""From the docstring."""'
        ),
    )
    (entry,) = scan.scan_all_prototypes(tmp_path)
    assert entry["title"] == "Partial"
    assert entry["subtitle"] == "From the docstring."
    assert entry["icon_path"] is None


def test_script_metadata_icon_cannot_escape_the_folder(tmp_path: Path) -> None:
    """An icon path outside the script's folder is ignored."""
    write(tmp_path / "outside.png", "png")
    write(
        tmp_path / "sub" / "s.py",
        script_with_metadata('[tool.stub_launcher]\nicon = "../outside.png"'),
    )
    (entry,) = scan.scan_all_prototypes(tmp_path / "sub")
    assert entry["icon_path"] is None


# ---------------------------------------------------------------------------
# Folder previews
# ---------------------------------------------------------------------------


def test_folder_summary_counts_each_kind(tmp_path: Path) -> None:
    """Subfolders, packages, scripts and other files are counted separately."""
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
    write(tmp_path / "proj" / "pyproject.toml", "[project]\nname='p'\n")
    write(tmp_path / "one.py")
    write(tmp_path / "two.py")
    write(tmp_path / "notes.txt")
    assert (
        scan.folder_summary(tmp_path)
        == "2 subfolders, 1 package, 2 scripts, 1 other file"
    )


def test_zipapps_count_as_packages_in_the_summary(tmp_path: Path) -> None:
    """A .pyz is a runnable package, not an "other file" (#124)."""
    write(tmp_path / "tool.pyz")
    write(tmp_path / "proj" / "pyproject.toml", "[project]\nname='p'\n")
    write(tmp_path / "notes.txt")
    assert scan.folder_summary(tmp_path) == "2 packages, 1 other file"
    assert scan.folder_summary_compact(tmp_path) == "📦 2 · 📄 1"


def test_compact_summary_uses_one_symbol_for_each_kind(tmp_path: Path) -> None:
    """Short enough for a narrow row: a symbol and a count, in a fixed order."""
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
    write(tmp_path / "proj" / "pyproject.toml", "[project]\nname='p'\n")
    write(tmp_path / "one.py")
    write(tmp_path / "two.py")
    write(tmp_path / "notes.txt")
    assert scan.folder_summary_compact(tmp_path) == "📁 2 · 📦 1 · 🐍 2 · 📄 1"
    assert len(scan.folder_summary_compact(tmp_path)) < len(
        scan.folder_summary(tmp_path)
    )


def test_compact_summary_leaves_out_empty_kinds_and_handles_no_folder(
    tmp_path: Path,
) -> None:
    """Only kinds present are shown; empty and unreadable folders still say so."""
    write(tmp_path / "only.py")
    assert scan.folder_summary_compact(tmp_path) == "🐍 1"
    empty = tmp_path / "empty"
    empty.mkdir()
    assert scan.folder_summary_compact(empty) == "Empty folder"
    assert scan.folder_summary_compact(tmp_path / "missing") == "Folder"


def test_folder_summary_skips_hidden_cache_and_launcher_files(tmp_path: Path) -> None:
    """Things the list never shows aren't counted either."""
    write(tmp_path / ".DS_Store")
    write(tmp_path / ".git" / "HEAD")
    write(tmp_path / "__pycache__" / "x.pyc")
    write(tmp_path / "patch_app.py")
    write(tmp_path / "__init__.py")
    write(tmp_path / "only.py")
    assert scan.folder_summary(tmp_path) == "1 script"


def test_folder_summary_empty_and_missing(tmp_path: Path) -> None:
    """An empty folder says so; an unreadable one falls back to "Folder"."""
    assert scan.folder_summary(tmp_path) == "Empty folder"
    assert scan.folder_summary(tmp_path / "missing") == "Folder"


def test_folder_rows_preview_their_contents(tmp_path: Path) -> None:
    """A folder row's subtitle is its contents summary, not just "Folder"."""
    write(tmp_path / "games" / "pong.py")
    write(tmp_path / "games" / "snake.py")
    (entry,) = scan.scan_all_prototypes(tmp_path)
    assert entry["subtitle"] == "🐍 2"


def test_script_and_project_aliases_are_read(tmp_path: Path) -> None:
    """[tool.stub_launcher.aliases] in PEP 723 or pyproject.toml is passed on (#79)."""
    write(
        tmp_path / "s.py",
        script_with_metadata(
            'dependencies = ["fast"]\n'
            "[tool.stub_launcher.aliases]\n"
            'fast = { kind = "substitute", target = "fast-pure" }'
        ),
    )
    write(
        tmp_path / "proj" / "pyproject.toml",
        "[project]\nname = 'proj'\n"
        "[tool.stub_launcher.aliases]\n"
        'thing = { kind = "bundled", target = "core-thing" }\n',
    )
    entries = {e["title"]: e for e in scan.scan_all_prototypes(tmp_path)}
    assert entries["s"]["aliases"] == {"fast": piplike.Alias("substitute", "fast-pure")}
    assert entries["proj"]["aliases"] == {
        "thing": piplike.Alias("bundled", "core-thing")
    }


def test_bad_alias_table_skips_the_entry(tmp_path: Path) -> None:
    """A malformed alias table is reported like other malformed metadata."""
    write(
        tmp_path / "s.py",
        script_with_metadata(
            '[tool.stub_launcher.aliases]\nfast = { kind = "rename", target = "x" }'
        ),
    )
    assert list(scan.scan_all_prototypes(tmp_path)) == []


# ---------------------------------------------------------------------------
# PEP 621 entry points (#94)
# ---------------------------------------------------------------------------

ENTRY_POINTS = """
[project]
name = "tools"
description = "Some tools"

[project.scripts]
zeta = "tools.cli:zeta"
alpha = "tools.cli:Alpha.run"

[project.gui-scripts]
window = "tools.gui:main"

[project.entry-points."tools.plugins"]
plug = "tools.plugins"
"""


def test_entry_points_of_every_kind() -> None:
    """Console, GUI and any other group are all read, sorted by name."""
    import tomllib

    meta = tomllib.loads(ENTRY_POINTS)["project"]
    entries = scan.project_entry_points(meta)
    assert [(e.name, e.kind, e.group, e.reference) for e in entries] == [
        ("alpha", "cli", "console_scripts", "tools.cli:Alpha.run"),
        ("plug", "other", "tools.plugins", "tools.plugins"),
        ("window", "gui", "gui_scripts", "tools.gui:main"),
        ("zeta", "cli", "console_scripts", "tools.cli:zeta"),
    ]
    assert [e.label for e in entries] == ["Console", "tools.plugins", "GUI", "Console"]


def test_malformed_entry_point_tables_are_skipped() -> None:
    """Tables or values of the wrong type are ignored rather than failing."""
    meta = {
        "scripts": ["not", "a", "table"],
        "gui-scripts": {"ok": "pkg:main", "bad": 3},
        "entry-points": {"group": "not a table"},
    }
    assert [e.name for e in scan.project_entry_points(meta)] == ["ok"]


def test_several_entry_points_make_a_package(tmp_path: Path) -> None:
    """The project opens like a folder listing its entry points."""
    write(tmp_path / "tools" / "pyproject.toml", ENTRY_POINTS)
    (entry,) = scan.scan_all_prototypes(tmp_path)
    assert entry["kind"] == "package"
    assert entry["title"] == "tools"
    assert "entry_point" not in entry
    assert entry["project_dir"] == tmp_path / "tools"
    rows = scan.entry_rows(entry)
    assert [(r["title"], r["subtitle"], r["kind"]) for r in rows] == [
        ("alpha", "Console · tools.cli:Alpha.run", "entry"),
        ("plug", "tools.plugins · tools.plugins", "entry"),
        ("window", "GUI · tools.gui:main", "entry"),
        ("zeta", "Console · tools.cli:zeta", "entry"),
    ]
    assert all(r["package_title"] == "tools" for r in rows)
    assert all(r["folder_root"] == tmp_path / "tools" / "src" for r in rows)


def test_one_entry_point_is_the_projects_implied_entry(tmp_path: Path) -> None:
    """With a single entry point, the project runs it when tapped."""
    write(
        tmp_path / "one" / "pyproject.toml",
        '[project]\nname = "one"\n[project.scripts]\nrun = "one.cli:main"\n',
    )
    (entry,) = scan.scan_all_prototypes(tmp_path)
    assert entry["kind"] == "project"
    assert entry["entry"].name == "run"


def test_explicit_entry_point_overrides_entry_points(tmp_path: Path) -> None:
    """[tool.stub_launcher] entry_point wins over [project.scripts]."""
    write(
        tmp_path / "tools" / "pyproject.toml",
        ENTRY_POINTS + '\n[tool.stub_launcher]\nentry_point = "main.py"\n',
    )
    (entry,) = scan.scan_all_prototypes(tmp_path)
    assert entry["kind"] == "project" and "entry" not in entry
    assert entry["entry_point"] == tmp_path / "tools" / "main.py"


def test_no_entry_points_falls_back_to_main_py(tmp_path: Path) -> None:
    """A [tool.stub_launcher] table without entry_point isn't an entry point."""
    write(
        tmp_path / "plain" / "pyproject.toml",
        '[project]\nname = "plain"\n[tool.stub_launcher]\ndisplay_name = "Plain"\n',
    )
    (entry,) = scan.scan_all_prototypes(tmp_path)
    assert entry["kind"] == "project" and "entry" not in entry
    assert entry["entry_point"] == tmp_path / "plain" / "main.py"
