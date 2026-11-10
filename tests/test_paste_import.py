"""Importing a script, file or archive from the pasteboard (#36).

The pasteboard itself is iOS-only (bridge.py); this is everything after it.
"""

import io
import tarfile
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from mypystub import paste_import


def test_default_filename_uses_the_time() -> None:
    """Pasted text is named for when it was pasted."""
    assert (
        paste_import.default_filename(datetime(2026, 11, 3, 9, 5))
        == "pasted_20261103_0905"
    )


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("tool", "tool.py"),
        ("tool.py", "tool.py"),
        ("TOOL.PY", "TOOL.PY"),
        ("test.py.py", "test.py"),
        ("test.PY.py", "test.PY"),
        ("test.py.py.py", "test.py"),
        ("notes.txt.txt", "notes.py"),  # pasted text is always Python
        ("release 1.2.2", "release 1.2.2.py"),  # a version is not an extension
        ("notes.txt", "notes.py"),  # never anything but .py
        ("  spaced name  ", "spaced name.py"),
        ("sub/dir/tool.py", "tool.py"),
        ("../../evil", "evil.py"),
        ("a\x00b\n", "ab.py"),
        ("", None),
        ("   ", None),
        (".", None),
        ("..", None),
    ],
)
def test_clean_filename(typed: str, expected: str | None) -> None:
    """Typed names lose folders and control characters, and gain .py."""
    assert paste_import.clean_filename(typed) == expected


def test_unique_path_increments_files_and_folders(tmp_path: Path) -> None:
    """An existing name is never reused: _2, _3, ... before the extension."""
    assert paste_import.unique_path(tmp_path, "a.py") == tmp_path / "a.py"
    (tmp_path / "a.py").write_text("")
    assert paste_import.unique_path(tmp_path, "a.py") == tmp_path / "a_2.py"
    (tmp_path / "a_2.py").write_text("")
    assert paste_import.unique_path(tmp_path, "a.py") == tmp_path / "a_3.py"
    (tmp_path / "proj").mkdir()
    assert paste_import.unique_path(tmp_path, "proj") == tmp_path / "proj_2"
    (tmp_path / "x.tar.gz").write_text("")
    assert paste_import.unique_path(tmp_path, "x.tar.gz") == tmp_path / "x_2.tar.gz"


@pytest.mark.parametrize(
    ("name", "archive"),
    [
        ("a.zip", True),
        ("A.ZIP", True),
        ("a.tar", True),
        ("a.tar.gz", True),
        ("a.tgz", True),
        ("a.pyz", False),  # runs as it is
        ("a.py", False),
        ("a.whl", False),
        ("zip", False),
    ],
)
def test_which_files_are_archives(name: str, archive: bool) -> None:
    """Archives are offered for extraction; a .pyz is a program, kept as it is."""
    assert paste_import.is_archive(name) is archive


def test_files_are_copied_as_they_are(tmp_path: Path) -> None:
    """Any of the normal extensions are accepted, bytes unchanged."""
    source = tmp_path / "in" / "tool.pyz"
    source.parent.mkdir()
    source.write_bytes(b"PK\x03\x04binary")
    dest = tmp_path / "out"
    dest.mkdir()
    result = paste_import.import_file(source, dest).path
    assert result == dest / "tool.pyz" and result.read_bytes() == b"PK\x03\x04binary"


def test_a_clash_keeps_the_new_name_and_the_old_as_a_version(tmp_path: Path) -> None:
    """The newest has the right name; what it replaced is kept beside it (#182)."""
    (tmp_path / "tool.py").write_text("old")
    now = datetime(2026, 11, 5, 14, 32, 7)
    imported = paste_import.import_text("new", "tool.py", tmp_path, now)
    assert imported.path == tmp_path / "tool.py" and imported.path.read_text() == "new"
    assert imported.previous == tmp_path / "backups" / "tool.2026-11-05T143207.py"
    assert imported.previous.read_text() == "old"
    assert not imported.unchanged
    fresh = paste_import.import_text("x", "other.py", tmp_path, now)
    assert fresh.previous is None


def test_pasting_what_is_already_there_changes_nothing(tmp_path: Path) -> None:
    """Identical content makes no new version."""
    (tmp_path / "tool.py").write_text("same")
    imported = paste_import.import_text("same", "tool.py", tmp_path)
    assert imported.unchanged and imported.previous is None
    assert sorted(p.name for p in tmp_path.iterdir()) == ["tool.py"]  # no backups/


def make_zip(path: Path, members: dict[str, str]) -> Path:
    """Write a zip of `members` (name to text)."""
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in members.items():
            archive.writestr(name, text)
    return path


def test_a_single_top_level_folder_is_used_as_it_is(tmp_path: Path) -> None:
    """proj/... extracts to proj, with no second folder around it."""
    archive = make_zip(tmp_path / "proj.zip", {"proj/a.py": "1", "proj/sub/b.py": "2"})
    dest = tmp_path / "docs"
    dest.mkdir()
    folder = paste_import.extract_archive(archive, dest)
    assert folder == dest / "proj"
    assert (folder / "a.py").read_text() == "1" and (folder / "sub" / "b.py").exists()


def test_loose_contents_get_a_folder_named_for_the_archive(tmp_path: Path) -> None:
    """Several top-level entries go into one folder named after the archive."""
    archive = make_zip(tmp_path / "tools.zip", {"a.py": "1", "b.py": "2"})
    dest = tmp_path / "docs"
    dest.mkdir()
    folder = paste_import.extract_archive(archive, dest)
    assert folder == dest / "tools" and sorted(p.name for p in folder.iterdir()) == [
        "a.py",
        "b.py",
    ]


def test_extraction_never_overwrites_a_folder(tmp_path: Path) -> None:
    """If the folder exists, the extracted one gets an incrementing name."""
    archive = make_zip(tmp_path / "proj.zip", {"proj/a.py": "new"})
    dest = tmp_path / "docs"
    (dest / "proj").mkdir(parents=True)
    (dest / "proj" / "a.py").write_text("old")
    folder = paste_import.extract_archive(archive, dest)
    assert folder == dest / "proj_2" and (folder / "a.py").read_text() == "new"
    assert (dest / "proj" / "a.py").read_text() == "old"
    assert [p.name for p in dest.iterdir() if p.name.startswith(".")] == []


def test_mac_zip_junk_is_ignored(tmp_path: Path) -> None:
    """Finder's __MACOSX folder doesn't count as a second top-level folder."""
    archive = make_zip(
        tmp_path / "proj.zip",
        {"proj/a.py": "1", "__MACOSX/proj/._a.py": "junk", "proj/.DS_Store": "x"},
    )
    dest = tmp_path / "docs"
    dest.mkdir()
    folder = paste_import.extract_archive(archive, dest)
    assert folder == dest / "proj"
    assert not (dest / "__MACOSX").exists() and not (folder / ".DS_Store").exists()


@pytest.mark.parametrize("member", ["../evil.py", "/abs/evil.py", "proj/../../evil.py"])
def test_unsafe_members_refuse_the_whole_archive(tmp_path: Path, member: str) -> None:
    """Nothing is extracted from an archive that tries to leave its folder."""
    archive = make_zip(tmp_path / "bad.zip", {"proj/a.py": "1", member: "x"})
    dest = tmp_path / "docs"
    dest.mkdir()
    with pytest.raises(ValueError, match="unsafe"):
        paste_import.extract_archive(archive, dest)
    assert list(dest.iterdir()) == []
    assert not (tmp_path / "evil.py").exists()


def test_tar_archives_extract_too(tmp_path: Path) -> None:
    """.tar.gz works like .zip."""
    archive = tmp_path / "proj.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        data = b"print(1)\n"
        info = tarfile.TarInfo("proj/a.py")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    dest = tmp_path / "docs"
    dest.mkdir()
    assert paste_import.extract_archive(archive, dest) == dest / "proj"
    assert (dest / "proj" / "a.py").read_bytes() == b"print(1)\n"


def test_the_extracted_name_for_an_archive_without_a_folder(tmp_path: Path) -> None:
    """A .tar.gz's folder name drops the whole compound extension."""
    archive = tmp_path / "tools.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name in ("a.py", "b.py"):
            info = tarfile.TarInfo(name)
            tar.addfile(info, io.BytesIO(b""))
    dest = tmp_path / "docs"
    dest.mkdir()
    assert paste_import.extract_archive(archive, dest) == dest / "tools"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("test.py.py", "test.py"),
        ("notes.txt.txt", "notes.txt"),
        ("a.TXT.txt", "a.TXT"),
        ("archive.tar.gz.gz", "archive.tar.gz"),
        ("test.py", "test.py"),
        ("notes.txt.py", "notes.txt.py"),
        ("release 1.2.2", "release 1.2.2"),
        ("data.v2.v2", "data.v2"),
        ("no_extension", "no_extension"),
    ],
)
def test_collapse_repeated_extension(name: str, expected: str) -> None:
    """The same extension twice at the end becomes one; nothing else changes."""
    assert paste_import.collapse_repeated_extension(name) == expected


def test_suggested_names_with_repeats_are_cleaned() -> None:
    """The name another app gives an item can't make test.py.py either."""
    now = datetime(2026, 11, 5, 9, 5)
    assert paste_import.suggested_stem("test.py.py", now) == "test"
    assert paste_import.suggested_stem("interest tracker.py", now) == "interest tracker"


def test_a_copied_file_loses_a_repeated_extension(tmp_path: Path) -> None:
    """Importing ``x.txt.txt`` writes ``x.txt``; the content is untouched."""
    source = tmp_path / "src"
    source.mkdir()
    (source / "x.txt.txt").write_text("hello")
    folder = tmp_path / "docs"
    folder.mkdir()
    written = paste_import.import_file(source / "x.txt.txt", folder).path
    assert written.name == "x.txt" and written.read_text() == "hello"


def test_an_archive_with_a_repeated_extension_names_its_folder_cleanly() -> None:
    """``a.zip.zip`` unpacks into ``a``, not ``a.zip``."""
    assert paste_import.archive_stem("a.zip.zip") == "a"
