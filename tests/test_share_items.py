"""What is sent when a script, project or zipapp is shared (#147)."""

import zipfile
from pathlib import Path

import pytest

from mypystub import paste_import, share_items


def make_project(root: Path) -> Path:
    """A project folder with things that should and shouldn't be shared."""
    project = root / "my project"
    files = {
        "pyproject.toml": "[project]\nname='p'\n",
        "src/p/__init__.py": "x = 1\n",
        "src/p/data/table.csv": "a,b\n",
        "README.md": "hello\n",
        "src/p/__pycache__/x.cpython-315.pyc": "junk",
        "build/lib/x.py": "built",
        "dist/p-1.whl": "built",
        "p.egg-info/PKG-INFO": "x",
        ".git/config": "secret",
        ".env": "TOKEN=1",
        ".DS_Store": "mac",
        "launcher.toml": "[run_with]\n",
    }
    for name, text in files.items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return project


def names(archive: Path) -> set[str]:
    """The file names in a zip."""
    with zipfile.ZipFile(archive) as zf:
        return set(zf.namelist())


def test_a_project_zip_has_one_top_folder_and_leaves_out_the_junk(
    tmp_path: Path,
) -> None:
    """Content under the project's own name; caches, git, secrets and Setup left out."""
    archive = share_items.zip_project(make_project(tmp_path), tmp_path / "out")
    assert archive.name == "my project.zip"
    assert names(archive) == {
        "my project/pyproject.toml",
        "my project/src/p/__init__.py",
        "my project/src/p/data/table.csv",
        "my project/README.md",
    }


def test_sharing_then_pasting_gives_the_project_back(tmp_path: Path) -> None:
    """The round trip: Paste extracts the zip into the same folder, same files."""
    project = make_project(tmp_path)
    archive = share_items.zip_project(project, tmp_path / "out")
    other = tmp_path / "other device"
    other.mkdir()
    extracted = paste_import.extract_archive(archive, other)
    assert extracted.name == "my project"
    assert (extracted / "src/p/data/table.csv").read_text() == "a,b\n"
    assert (extracted / "README.md").read_text() == "hello\n"
    assert not (extracted / ".git").exists()


def test_a_script_or_zipapp_is_shared_as_it_is(tmp_path: Path) -> None:
    """The file itself goes to the share sheet; nothing is copied."""
    for name in ("tool.py", "app.pyz"):
        path = tmp_path / name
        path.write_text("x")
        assert share_items.prepare_share(path, tmp_path / "cache") == path
    assert not (tmp_path / "cache").exists()


def test_a_folder_is_zipped_in_the_cache_and_the_last_share_is_cleared(
    tmp_path: Path,
) -> None:
    """Old shares don't pile up."""
    project = make_project(tmp_path)
    cache = tmp_path / "cache"
    first = share_items.prepare_share(project, cache)
    stale = cache / "share" / "old.zip"
    stale.write_text("old")
    second = share_items.prepare_share(project, cache)
    assert first == second == cache / "share" / "my project.zip"
    assert not stale.exists()


def test_a_missing_thing_is_reported(tmp_path: Path) -> None:
    """A row whose file has gone says so."""
    with pytest.raises(FileNotFoundError, match="isn't there"):
        share_items.prepare_share(tmp_path / "gone.py", tmp_path / "cache")


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("src/p/mod.py", False),
        ("src/p/__pycache__/m.pyc", True),
        ("p.egg-info/x", True),
        (".git/HEAD", True),
        ("a/.hidden", True),
        ("launcher.toml", True),
        ("docs/launcher.toml", True),
        ("build.py", False),
    ],
)
def test_skipped(relative: str, expected: bool) -> None:
    """Exclusion applies to any part of the path, not substrings of names."""
    assert share_items.skipped(Path(relative)) is expected
