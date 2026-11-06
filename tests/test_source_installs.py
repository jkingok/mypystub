"""Reading and installing a pure-Python source tree without building it (#172)."""

import importlib
import importlib.metadata
import sys
from pathlib import Path

import pytest
from packaging.version import Version

from mypystub import source_installs as si
from tests.support_sources import TOGA_CONSOLE_LIKE, make_zip, write_tree


@pytest.mark.parametrize(
    ("url", "archive"),
    [
        ("https://github.com/o/r", "https://github.com/o/r/archive/HEAD.zip"),
        ("https://github.com/o/r.git", "https://github.com/o/r/archive/HEAD.zip"),
        ("https://github.com/o/r/", "https://github.com/o/r/archive/HEAD.zip"),
        ("https://github.com/o/r/tree/v1.2", "https://github.com/o/r/archive/v1.2.zip"),
        (
            "git+https://github.com/o/r.git@v1.2",
            "https://github.com/o/r/archive/v1.2.zip",
        ),
        (
            "git+https://github.com/o/r.git@main#subdirectory=pkg",
            "https://github.com/o/r/archive/main.zip#subdirectory=pkg",
        ),
        (
            "https://github.com/o/r/tree/feature/x#sha256=ab",
            "https://github.com/o/r/archive/feature/x.zip#sha256=ab",
        ),
    ],
)
def test_github_urls_become_archive_urls(url: str, archive: str) -> None:
    """The known GitHub pattern, with the ref and the fragment kept."""
    assert si.github_archive_url(url) == archive


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/o",
        "https://github.com/o/r/issues/1",
        "https://github.com/o/r/blob/main/x.py",
        "https://gitlab.com/o/r",
        "git+ssh://git@github.com/o/r.git",
        "https://example.com/github.com/o/r",
    ],
)
def test_other_urls_are_not_github_repositories(url: str) -> None:
    """Files, issues, other hosts and SSH are not translated."""
    assert si.github_archive_url(url) is None


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


def read(tmp_path: Path, files: dict | None = None, url: str = "https://h/a.zip"):
    """Write a tree and read it as a project."""
    root = write_tree(tmp_path / "tree", files or TOGA_CONSOLE_LIKE)
    return si.read_project(root, url, "toga_console")


def test_a_toga_console_like_project_is_read_from_static_metadata(
    tmp_path: Path,
) -> None:
    """Name, dependencies, entry points and packages come from pyproject."""
    project = read(tmp_path)
    assert project.name == "toga-console"
    assert project.requires == ["toga-core >= 0.5.7, < 0.6"]
    assert project.entry_points == {
        "toga_console.backend.toga_dummy": {
            "Console": "toga_console.platforms.dummy:Console"
        }
    }
    assert [p.name for p in project.packages] == ["toga_console"]  # not tests/examples


def test_a_dynamic_version_comes_from_the_archive_or_the_ref(tmp_path: Path) -> None:
    """setuptools_scm's .git_archival.txt, then the ref in the URL, then unknown."""
    assert read(tmp_path).version == Version("0.1.0")
    files = {k: v for k, v in TOGA_CONSOLE_LIKE.items() if k != ".git_archival.txt"}
    by_ref = read(tmp_path / "b", files, "https://github.com/o/r/archive/v2.3.zip")
    assert by_ref.version == Version("2.3")
    unknown = read(tmp_path / "c", files, "https://github.com/o/r/archive/HEAD.zip")
    assert unknown.version == Version("0+unknown")


def test_a_flat_layout_is_found(tmp_path: Path) -> None:
    """No src folder: top-level packages and modules, but not tests or setup.py."""
    files = {
        "pyproject.toml": TOGA_CONSOLE_LIKE["pyproject.toml"],
        "toga_console/__init__.py": "",
        "single.py": "",
        "setup.py": "",
        "tests/test_x.py": "",
    }
    names = sorted(p.name for p in read(tmp_path, files).packages)
    assert names == ["single.py", "toga_console"]


def test_the_wrong_project_is_refused(tmp_path: Path) -> None:
    """The archive must hold the project the requirement names."""
    root = write_tree(tmp_path / "t", TOGA_CONSOLE_LIKE)
    with pytest.raises(si.SourceProblem, match="not other"):
        si.read_project(root, "https://h/a.zip", "other")


@pytest.mark.parametrize(
    ("files", "fragment"),
    [
        ({"x.py": "1"}, "no pyproject.toml"),
        (
            {"pyproject.toml": "[build-system]\nrequires=[]\n", "x.py": "1"},
            "[project] name",
        ),
        (
            {
                "pyproject.toml": TOGA_CONSOLE_LIKE["pyproject.toml"].replace(
                    'dynamic = ["version"]', 'dynamic = ["version", "dependencies"]'
                ),
                "src/toga_console/__init__.py": "",
            },
            "its dependencies are worked out",
        ),
        (
            {
                "pyproject.toml": TOGA_CONSOLE_LIKE["pyproject.toml"].replace(
                    'dynamic = ["version"]', 'dynamic = ["version", "license"]'
                ),
                "src/toga_console/__init__.py": "",
            },
            "its license is worked out",
        ),
        (
            {
                "pyproject.toml": TOGA_CONSOLE_LIKE["pyproject.toml"].replace(
                    'dynamic = ["version"]', 'dynamic = ["license", "urls"]'
                ),
                "src/toga_console/__init__.py": "",
            },
            "its license and urls are worked out",
        ),
        ({"pyproject.toml": TOGA_CONSOLE_LIKE["pyproject.toml"]}, "no Python package"),
    ],
)
def test_projects_that_cannot_be_read_without_a_build_are_refused(
    tmp_path: Path, files: dict, fragment: str
) -> None:
    """Each says why."""
    with pytest.raises(si.SourceProblem, match=fragment.replace("[", r"\[")):
        read(tmp_path, files)


def test_install_makes_an_importable_distribution_with_entry_points(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Files copied, package data included, and dist-info that Python can read."""
    project = read(tmp_path)
    target = tmp_path / "site"
    si.install(project, target)
    assert (target / "toga_console" / "data" / "hello.txt").read_text() == "hello\n"
    assert not (target / "tests").exists() and not (target / "examples").exists()
    monkeypatch.syspath_prepend(str(target))
    for name in [n for n in sys.modules if n.startswith("toga_console")]:
        monkeypatch.delitem(sys.modules, name)
    importlib.invalidate_caches()
    assert importlib.import_module("toga_console").VALUE == "console"
    dist = importlib.metadata.distribution("toga-console")
    assert dist.version == "0.1.0"
    points = [
        e for e in dist.entry_points if e.group == "toga_console.backend.toga_dummy"
    ]
    assert [e.value for e in points] == ["toga_console.platforms.dummy:Console"]
    assert dist.requires == [
        "toga-core >= 0.5.7, < 0.6",
        "rich>=13; (python_version >= '3.10') and extra == 'extra'",
    ]
    assert (target / "toga_console-0.1.0.dist-info" / "RECORD").read_text().count(
        "\n"
    ) > 5
