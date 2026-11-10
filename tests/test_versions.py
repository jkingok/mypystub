"""Backups of what a paste replaces (#182). No Toga needed."""

import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from mypystub import paste_import, scan, versions

NOW = datetime(2026, 11, 5, 14, 32, 7)
LATER = datetime(2026, 11, 6, 9, 0, 0)


def make_project(folder: Path, body: str = "print(1)\n") -> Path:
    folder.mkdir()
    (folder / "pyproject.toml").write_text("[project]\nname='p'\nversion='1'\n")
    (folder / "main.py").write_text(body)
    return folder


def test_a_file_is_copied_with_the_time_before_its_extension(tmp_path: Path) -> None:
    (tmp_path / "tool.py").write_text("old")
    backup = versions.back_up(tmp_path / "tool.py", NOW)
    assert backup == tmp_path / "backups" / "tool.2026-11-05T143207.py"
    assert backup.read_text() == "old" and (tmp_path / "tool.py").exists()


def test_a_folder_is_zipped(tmp_path: Path) -> None:
    project = make_project(tmp_path / "proj")
    backup = versions.back_up(project, NOW)
    assert backup == tmp_path / "backups" / "proj.2026-11-05T143207.zip"
    with zipfile.ZipFile(backup) as z:
        assert sorted(z.namelist()) == ["main.py", "pyproject.toml"]


def test_list_backups_finds_files_and_folders_newest_first(tmp_path: Path) -> None:
    (tmp_path / "tool.py").write_text("a")
    (tmp_path / "other.py").write_text("z")
    versions.back_up(tmp_path / "tool.py", NOW)
    versions.back_up(tmp_path / "other.py", NOW)
    versions.back_up(tmp_path / "tool.py", LATER)
    listed = versions.list_backups(tmp_path / "tool.py")
    assert [b.when for b in listed] == [LATER, NOW]
    assert not listed[0].is_folder
    project = make_project(tmp_path / "proj")
    versions.back_up(project, NOW)
    only = versions.list_backups(project)
    assert len(only) == 1 and only[0].is_folder


def test_the_backups_folder_is_hidden_from_the_list(tmp_path: Path) -> None:
    (tmp_path / "tool.py").write_text("print(1)\n")
    versions.back_up(tmp_path / "tool.py", NOW)
    titles = [row["title"] for row in scan.scan_all_prototypes(tmp_path)]
    assert titles == ["tool"]
    counts = scan.folder_counts(tmp_path)
    assert counts is not None and counts["subfolder"] == 0


def test_hash_covers_names_and_content_of_folders(tmp_path: Path) -> None:
    one = make_project(tmp_path / "one")
    two = make_project(tmp_path / "two")
    assert versions.same_content(one, two)
    (two / "main.py").write_text("print(2)\n")
    assert not versions.same_content(one, two)
    (two / "main.py").write_text("print(1)\n")
    (two / "extra.txt").write_text("x")
    assert not versions.same_content(one, two)


def test_restore_backs_up_the_current_and_keeps_the_backup(tmp_path: Path) -> None:
    tool = tmp_path / "tool.py"
    tool.write_text("v1")
    old = versions.back_up(tool, NOW)
    tool.write_text("v2")
    previous = versions.restore(old, tool, LATER)
    assert tool.read_text() == "v1"
    assert previous is not None and previous.read_text() == "v2"
    assert old.exists()


def test_restore_a_project_folder(tmp_path: Path) -> None:
    project = make_project(tmp_path / "proj", "print('v1')\n")
    old = versions.back_up(project, NOW)
    (project / "main.py").write_text("print('v2')\n")
    (project / "new.py").write_text("x")
    versions.restore(old, project, LATER)
    assert (project / "main.py").read_text() == "print('v1')\n"
    assert not (project / "new.py").exists()
    assert len(versions.list_backups(project)) == 2


def test_delete_only_removes_backups(tmp_path: Path) -> None:
    tool = tmp_path / "tool.py"
    tool.write_text("a")
    backup = versions.back_up(tool, NOW)
    with pytest.raises(ValueError):
        versions.delete(tool)
    versions.delete(backup)
    assert not backup.exists() and tool.exists()


def test_pasting_a_file_over_one_backs_it_up(tmp_path: Path) -> None:
    (tmp_path / "tool.py").write_text("old")
    source = tmp_path / "src" / "tool.py"
    source.parent.mkdir()
    source.write_text("new")
    result = paste_import.import_file(source, tmp_path, NOW)
    assert (tmp_path / "tool.py").read_text() == "new"
    assert result.previous is not None and result.previous.read_text() == "old"
    assert result.previous.parent == tmp_path / "backups"


def test_pasting_the_same_file_or_text_changes_nothing(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "tool.py").write_text("same")
    source = tmp_path / "tool.py"
    source.write_text("same")
    assert paste_import.import_file(source, docs, NOW).unchanged
    assert paste_import.import_text("same", "tool.py", docs, NOW).unchanged
    assert not (docs / "backups").exists()


def test_pasting_text_over_a_script_backs_it_up(tmp_path: Path) -> None:
    (tmp_path / "t.py").write_text("old")
    result = paste_import.import_text("new", "t.py", tmp_path, NOW)
    assert (tmp_path / "t.py").read_text() == "new" and result.previous is not None


def make_zip(path: Path, body: str) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("proj/pyproject.toml", "[project]\nname='p'\nversion='1'\n")
        z.writestr("proj/main.py", body)
    return path


def test_an_archive_over_a_project_zips_the_old_folder(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    first = paste_import.store_archive(make_zip(tmp_path / "a.zip", "1"), docs, NOW)
    assert first.previous is None and (docs / "proj" / "main.py").read_text() == "1"
    second = paste_import.store_archive(make_zip(tmp_path / "b.zip", "2"), docs, LATER)
    assert (docs / "proj" / "main.py").read_text() == "2"
    assert second.previous is not None and second.previous.suffix == ".zip"
    assert sorted(p.name for p in docs.iterdir() if not p.name.startswith(".")) == [
        "backups",
        "proj",
    ]


def test_the_same_archive_again_changes_nothing_for_folders(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    paste_import.store_archive(make_zip(tmp_path / "a.zip", "1"), docs, NOW)
    again = paste_import.store_archive(make_zip(tmp_path / "c.zip", "1"), docs, LATER)
    assert again.unchanged and not (docs / "backups").exists()
