"""Building a wheel in-process with the project's own backend (#257)."""

import os
import sys
from pathlib import Path

import pytest

from mypystub import source_build as sb
from tests.support_sources import FAKE_BACKEND, write_tree

PYPROJECT = """
[build-system]
requires = ["fakebackend"]
build-backend = "fakebackend"

[project]
name = "demo"
version = "1.0"
"""


@pytest.fixture
def site(tmp_path: Path) -> Path:
    folder = tmp_path / "backend"
    folder.mkdir()
    (folder / "fakebackend.py").write_text(FAKE_BACKEND)
    return folder


def tree(tmp_path: Path, **extra: str) -> Path:
    return write_tree(
        tmp_path / "demo",
        {"pyproject.toml": PYPROJECT, "src/demo/__init__.py": "X = 1\n", **extra},
    )


def test_build_system_defaults_to_setuptools(tmp_path: Path) -> None:
    """No [build-system] (a Briefcase project's may have none): pip's default."""
    root = write_tree(tmp_path, {"pyproject.toml": "[tool.briefcase]\n"})
    system = sb.build_system(root)
    assert system.backend == "setuptools.build_meta:__legacy__"
    assert system.requires == ("setuptools>=40.8.0",)


def test_build_system_is_read(tmp_path: Path) -> None:
    root = write_tree(
        tmp_path,
        {
            "pyproject.toml": '[build-system]\nrequires = ["flit_core"]\n'
            'build-backend = "flit_core.buildapi"\nbackend-path = ["tools"]\n'
        },
    )
    assert sb.build_system(root) == sb.BuildSystem(
        ("flit_core",), "flit_core.buildapi", ("tools",)
    )


def test_a_wheel_is_built_and_the_source_is_untouched(
    tmp_path: Path, site: Path
) -> None:
    root = tree(tmp_path)
    before = sorted(p.relative_to(root) for p in root.rglob("*"))
    wheel = sb.build_wheel(root, site, tmp_path / "out")
    assert wheel.name == "demo-1.0-py3-none-any.whl"
    assert sorted(p.relative_to(root) for p in root.rglob("*")) == before


def test_a_version_is_handed_to_version_plugins(tmp_path: Path, site: Path) -> None:
    root = tree(tmp_path)
    (root / "pyproject.toml").write_text(PYPROJECT.replace('version = "1.0"', ""))
    wheel = sb.build_wheel(root, site, tmp_path / "out", version="2.5")
    assert wheel.name == "demo-2.5-py3-none-any.whl"
    assert "SETUPTOOLS_SCM_PRETEND_VERSION" not in os.environ  # put back


def test_systemexit_from_a_backend_is_a_build_problem(
    tmp_path: Path, site: Path
) -> None:
    """setuptools exits on errors; that must not end the app."""
    root = tree(tmp_path, **{"src/demo/fast.c": "int x;"})
    with pytest.raises(sb.BuildProblem, match="can't run here.*no compiler"):
        sb.build_wheel(root, site, tmp_path / "out")


def test_processes_are_blocked_during_a_build_and_restored(
    tmp_path: Path, site: Path
) -> None:
    import subprocess

    original = subprocess.Popen
    (site / "spawner.py").write_text(
        "import subprocess\n"
        "def build_wheel(d, c=None, m=None):\n"
        "    subprocess.Popen(['cc'])\n"
    )
    root = tree(tmp_path)
    with pytest.raises(sb.BuildProblem, match="process"):
        sb.build_wheel(
            root, site, tmp_path / "out", system=sb.BuildSystem((), "spawner")
        )
    assert subprocess.Popen is original


def test_the_process_is_left_as_it_was(tmp_path: Path, site: Path) -> None:
    before = (list(sys.path), os.getcwd(), dict(os.environ), list(sys.meta_path))
    sb.build_wheel(tree(tmp_path), site, tmp_path / "out")
    assert "fakebackend" not in sys.modules
    assert (
        list(sys.path),
        os.getcwd(),
        dict(os.environ),
        list(sys.meta_path),
    ) == before


def test_an_in_tree_backend_path_may_not_leave_the_project(
    tmp_path: Path, site: Path
) -> None:
    with pytest.raises(sb.BuildProblem, match="leaves the project"):
        sb.build_wheel(
            tree(tmp_path),
            site,
            tmp_path / "out",
            system=sb.BuildSystem((), "fakebackend", ("../elsewhere",)),
        )
