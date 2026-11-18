"""Fetching and unpacking the source a requirement points at (#172, #257)."""

from pathlib import Path

import pytest

from mypystub import source_installs as si
from tests.support_sources import TOGA_CONSOLE_LIKE, make_zip, write_tree


def test_gitlab_and_bitbucket_archives_name_their_ref() -> None:
    """The version hint reads the ref from each host's archive URL."""
    assert si.ref_of("https://gitlab.com/g/s/r/-/archive/v1.2/r-v1.2.zip") == "v1.2"
    assert si.ref_of("https://bitbucket.org/w/r/get/v1.2.zip") == "v1.2"


def test_subdirectory_and_ref() -> None:
    """#subdirectory= is read from the fragment; the ref from the file name."""
    assert (
        si.subdirectory("https://h/a.zip#subdirectory=pkg/sub&sha256=ab") == "pkg/sub"
    )
    assert si.subdirectory("https://h/a.zip") == ""
    assert si.ref_of("https://github.com/o/r/archive/v1.2.zip") == "v1.2"
    assert si.ref_of("https://h/foo-1.0.tar.gz#x=1") == "foo-1.0"


def archive_file(tmp_path: Path, files: dict, top: str = "project-main") -> Path:
    """Write a GitHub-style zip to disk."""
    path = tmp_path / "a.zip"
    path.write_bytes(make_zip(files, top))
    return path


def test_extract_returns_the_single_top_folder(tmp_path: Path) -> None:
    """GitHub puts everything in one folder; that is the project root."""
    root = si.extract(archive_file(tmp_path, {"x.py": "1"}), tmp_path / "out")
    assert root.name == "project-main" and (root / "x.py").exists()


def test_extract_without_a_top_folder_uses_the_archive_root(tmp_path: Path) -> None:
    """Loose files at the top level are the project."""
    root = si.extract(archive_file(tmp_path, {"x.py": "1"}, top=""), tmp_path / "out")
    assert root == tmp_path / "out"


def test_extract_refuses_paths_that_escape(tmp_path: Path) -> None:
    """A path outside the folder refuses the whole archive."""
    path = tmp_path / "evil.zip"
    path.write_bytes(make_zip({"../evil.py": "1"}, top=""))
    with pytest.raises(si.SourceProblem, match="unsafe path"):
        si.extract(path, tmp_path / "out")
    assert not (tmp_path / "evil.py").exists()


def test_a_version_for_plugins_comes_from_the_archive_or_the_ref(
    tmp_path: Path,
) -> None:
    """setuptools_scm's .git_archival.txt, then the ref in the URL, then the commit."""
    root = write_tree(tmp_path / "a", TOGA_CONSOLE_LIKE)
    assert si.version_hint(root, "https://h/a.zip") == "0.1.0"
    bare = write_tree(tmp_path / "b", {"pyproject.toml": ""})
    assert si.version_hint(bare, "https://github.com/o/r/archive/v2.3.zip") == "2.3"
    assert si.version_hint(bare, "https://github.com/o/r/archive/HEAD.zip") == (
        "0+unknown"
    )
    assert (
        si.version_hint(bare, "https://github.com/o/r/archive/HEAD.zip", "abc1234def")
        == "0+gabc1234"
    )


def test_archival_describe_with_distance_becomes_a_post_release(tmp_path: Path) -> None:
    root = write_tree(
        tmp_path, {".git_archival.txt": "describe-name: v1.4.0-3-gabcdef1\n"}
    )
    assert si.version_from_archival(root) == "1.4.0.post3"


def test_open_source_honours_the_subdirectory(tmp_path: Path) -> None:
    archive = tmp_path / "a.zip"
    archive.write_bytes(make_zip({"pkg/pyproject.toml": "", "README": "x"}))
    assert si.open_source(archive, "https://h/a.zip#subdirectory=pkg").name == "pkg"
    with pytest.raises(si.SourceProblem, match="no folder called nope"):
        si.open_source(archive, "https://h/a.zip#subdirectory=nope")
