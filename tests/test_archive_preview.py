"""The Info page for what an archive unpacks to (#189)."""

import tarfile
import zipfile
from pathlib import Path

import pytest

from mypystub import archive_preview

PROJECT = """\
[project]
name = "hello-thing"
version = "2.1"
description = "Says hello."
dependencies = ["rich>=13"]

[project.scripts]
hello = "hello_thing:main"
"""


def zip_of(path: Path, files: dict[str, str]) -> Path:
    """Write a zip of `files` (path -> text)."""
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return path


def test_a_project_archive_shows_the_projects_info(tmp_path: Path) -> None:
    """Name, version, description and dependencies, as Info shows a project."""
    archive = zip_of(
        tmp_path / "hello.zip",
        {
            "hello-thing/pyproject.toml": PROJECT,
            "hello-thing/src/hello_thing/__init__.py": "def main(): ...\n",
        },
    )
    page = archive_preview.archive_info_html(archive, tmp_path / "scratch")
    assert "<h1>hello-thing</h1>" in page and "Says hello." in page
    assert "Version: 2.1" in page and "rich&gt;=13" in page
    assert "Archive contents" in page and "hello-thing" in page
    assert "Import extracts these into a new folder here." in page


@pytest.mark.parametrize(
    ("pyproject", "heading"),
    [
        ('[project]\nname = "demo-project"\n', "demo-project"),
        (
            '[project]\nname = "demo-project"\n[tool.stub_launcher]\n'
            + 'display_name = "Demo Project"\n',
            "Demo Project",
        ),
        ("not toml [", "demo_project"),
    ],
)
def test_a_project_is_headed_with_the_name_info_will_give_it(
    tmp_path: Path, pyproject: str, heading: str
) -> None:
    """Its display name or project name, as the list shows; else the folder's."""
    archive = zip_of(
        tmp_path / "demo_project.zip", {"demo_project/pyproject.toml": pyproject}
    )
    page = archive_preview.archive_info_html(archive, tmp_path / "scratch")
    assert page.startswith(f"<h1>{heading}</h1>")


def test_a_folder_archive_shows_its_readme(tmp_path: Path) -> None:
    """No project: the README, like a folder's Info."""
    archive = zip_of(
        tmp_path / "pack.zip",
        {"pack/README.md": "# Pack\n\nSome scripts.\n", "pack/a.py": "print(1)\n"},
    )
    page = archive_preview.archive_info_html(archive, tmp_path / "scratch")
    assert "Some scripts." in page


def test_a_folder_archive_without_a_readme_says_what_it_holds(tmp_path: Path) -> None:
    """The folder summary, with a hint to add a README."""
    archive = zip_of(tmp_path / "bare.zip", {"bare/a.py": "print(1)\n"})
    page = archive_preview.archive_info_html(archive, tmp_path / "scratch")
    assert "has no README to show" in page and "1 script" in page


def test_loose_files_use_the_archives_name(tmp_path: Path) -> None:
    """No top-level folder: the archive's name is the title."""
    archive = zip_of(tmp_path / "loose.zip", {"a.py": "x = 1\n", "b.py": "y = 2\n"})
    page = archive_preview.archive_info_html(archive, tmp_path / "scratch")
    assert "loose" in page and "2 scripts" in page


def test_a_tar_archive_works_too(tmp_path: Path) -> None:
    """tar.gz is previewed like a zip."""
    source = tmp_path / "src"
    (source / "t").mkdir(parents=True)
    (source / "t" / "pyproject.toml").write_text(PROJECT)
    archive = tmp_path / "t.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(source / "t", arcname="t")
    assert "Says hello." in archive_preview.archive_info_html(
        archive, tmp_path / "scratch"
    )


def test_the_scratch_folder_is_left_empty(tmp_path: Path) -> None:
    """Nothing from the preview is kept."""
    archive = zip_of(tmp_path / "a.zip", {"a/x.py": "1\n"})
    scratch = tmp_path / "scratch"
    archive_preview.archive_info_html(archive, scratch)
    assert list(scratch.iterdir()) == []


def test_a_big_archive_lists_its_contents_without_unpacking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Over the limit: no extraction, just the listing."""
    monkeypatch.setattr(archive_preview, "PREVIEW_LIMIT", 5)
    archive = zip_of(tmp_path / "big.zip", {"big/x.py": "print('a long line')\n"})
    scratch = tmp_path / "scratch"
    page = archive_preview.archive_info_html(archive, scratch)
    assert "too big to preview" in page and "Archive contents" in page
    assert not scratch.exists()


def test_an_unsafe_archive_is_refused(tmp_path: Path) -> None:
    """A path that escapes raises, for the caller to report."""
    archive = zip_of(tmp_path / "evil.zip", {"../evil.py": "x"})
    with pytest.raises(ValueError, match="unsafe"):
        archive_preview.archive_info_html(archive, tmp_path / "scratch")
