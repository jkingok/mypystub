"""Naming and making a new folder (mypystub.folders)."""

from pathlib import Path

import pytest

from mypystub.folders import clean_foldername, folder_name_problem, make_folder


@pytest.mark.parametrize(
    ("typed", "name"),
    [
        ("Projects", "Projects"),
        ("  padded  ", "padded"),
        ("with space", "with space"),
        ("a/b", "b"),  # only the last part: no folders made elsewhere
        ("../../escape", "escape"),
        ("a\\b", "b"),
        ("tab\there\n", "tabhere"),
        ("/", ""),
        ("..", ".."),
        ("", ""),
    ],
)
def test_names_are_cleaned_to_one_folder_name(typed: str, name: str) -> None:
    """Paths and control characters are dropped from what's typed."""
    assert clean_foldername(typed) == name


@pytest.mark.parametrize("name", ["Projects", "my tools", "v2", "naïve", "a.b"])
def test_ordinary_names_are_fine(name: str) -> None:
    """Spaces, digits, accents and inner dots are allowed."""
    assert folder_name_problem(name) is None


@pytest.mark.parametrize(
    ("name", "problem"),
    [
        ("", "Enter a name"),
        (".", "Enter a name"),
        ("..", "Enter a name"),
        (".hidden", "dot"),
        ("__pycache__", "leaves out"),
        ("site-packages", "leaves out"),
        ("site_packages", "leaves out"),
    ],
)
def test_names_the_list_would_hide_are_refused(name: str, problem: str) -> None:
    """A folder the list leaves out would vanish, so it can't be made."""
    result = folder_name_problem(name)
    assert result is not None and problem in result


def test_make_folder_creates_it(tmp_path: Path) -> None:
    """The folder is made inside the parent and returned."""
    made = make_folder(tmp_path, "new")
    assert made == tmp_path / "new" and made.is_dir()


def test_make_folder_never_replaces_anything(tmp_path: Path) -> None:
    """A folder or a file of that name is left alone."""
    (tmp_path / "taken").mkdir()
    (tmp_path / "taken" / "keep.py").write_text("x")
    (tmp_path / "file").write_text("x")
    with pytest.raises(FileExistsError):
        make_folder(tmp_path, "taken")
    with pytest.raises(FileExistsError):
        make_folder(tmp_path, "file")
    assert (tmp_path / "taken" / "keep.py").read_text() == "x"
    assert (tmp_path / "file").is_file()
