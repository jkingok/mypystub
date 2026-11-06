"""Reading what a source tree declares, in each format, without running it (#172)."""

import importlib
import sys
import zipfile
from pathlib import Path

import pytest
from packaging.version import Version

from mypystub import source_installs as si
from tests.support_sources import make_zip, write_tree

URL = "https://github.com/o/r/archive/HEAD.zip"
POETRY = """
[build-system]
requires = ["poetry-core>=1.0.0"]
build-backend = "poetry.core.masonry.api"

[tool.poetry]
name = "fancy"
version = "15.0.0"
description = "Fancy output"

[tool.poetry.dependencies]
python = ">=3.9.0"
pygments = "^2.13.0"
oldthing = "^0.2.3"
tilde = "~1.2.3"
exact = "1.5"
anything = "*"
ipywidgets = { version = ">=7.5.1,<9", optional = true }

[tool.poetry.extras]
jupyter = ["ipywidgets"]

[tool.poetry.scripts]
fancy = "fancy.cli:main"
"""
SETUP_CFG = """
[metadata]
name = plug
description = Hooks

[options]
packages =
    plug
python_requires = >=3.8
package_dir =
    =src
install_requires =
    colorama
    tomli>=2; python_version < "3.11"

[options.extras_require]
dev =
    tox

[options.entry_points]
console_scripts =
    plug = plug.cli:main
"""
SCM = """
[build-system]
requires = ["setuptools>=45", "setuptools-scm[toml]>=6.2.3"]
build-backend = "setuptools.build_meta"

[tool.setuptools_scm]
write_to = "src/plug/_version.py"
"""


def read(
    root: Path, files: dict, name: str | None = None, url: str = URL
) -> si.Project:
    """Write `files` under `root` and read the project there."""
    return si.read_project(write_tree(root, files), url, name)


def test_poetrys_own_table_is_read(tmp_path: Path) -> None:
    """Caret, tilde and optional dependencies become ordinary requirements."""
    project = read(
        tmp_path, {"pyproject.toml": POETRY, "fancy/__init__.py": ""}, "fancy"
    )
    assert project.version == Version("15.0.0")
    assert project.requires_python == ">=3.9.0"
    assert project.summary == "Fancy output"
    assert sorted(project.requires) == [
        "anything",
        "exact==1.5",
        "oldthing>=0.2.3,<0.3.0",
        "pygments>=2.13.0,<3.0.0",
        "tilde>=1.2.3,<1.3.0",
    ]
    assert project.extras == {"jupyter": ["ipywidgets>=7.5.1,<9"]}
    assert project.entry_points == {"console_scripts": {"fancy": "fancy.cli:main"}}


def test_a_poetry_source_dependency_is_refused(tmp_path: Path) -> None:
    """A dependency at a path or in git can't be written as a requirement here."""
    pyproject = POETRY.replace(
        'exact = "1.5"', 'exact = { git = "https://example.com/e.git" }'
    )
    with pytest.raises(si.SourceProblem, match="exact"):
        read(tmp_path, {"pyproject.toml": pyproject, "fancy/__init__.py": ""})


def test_setup_cfg_is_read(tmp_path: Path) -> None:
    """A setuptools project with its metadata in setup.cfg, and a version from git."""
    project = read(
        tmp_path,
        {
            "pyproject.toml": SCM,
            "setup.cfg": SETUP_CFG,
            "setup.py": "from setuptools import setup\nsetup(use_scm_version=True)\n",
            "src/plug/__init__.py": "",
        },
        "plug",
        "https://github.com/o/r/archive/1.5.0.zip",
    )
    assert project.name == "plug"
    assert project.version == Version("1.5.0")
    assert project.requires_python == ">=3.8"
    assert project.requires == ["colorama", 'tomli>=2; python_version < "3.11"']
    assert project.extras == {"dev": ["tox"]}
    assert project.entry_points == {"console_scripts": {"plug": "plug.cli:main"}}
    assert [p.name for p in project.packages] == ["plug"]


def test_setup_cfg_without_a_pyproject_is_read_too(tmp_path: Path) -> None:
    """The setup.py only calls setup(), so it says nothing the file doesn't."""
    project = read(
        tmp_path,
        {
            "setup.cfg": SETUP_CFG.replace("name = plug", "name = plug\nversion = 2.0"),
            "setup.py": "from setuptools import setup\nsetup()\n",
            "src/plug/__init__.py": "",
        },
    )
    assert project.version == Version("2.0")


def test_a_setup_py_that_lists_requirements_is_refused(tmp_path: Path) -> None:
    """They'd only be known by running it."""
    with pytest.raises(si.SourceProblem, match="setup.py"):
        read(
            tmp_path,
            {
                "setup.cfg": SETUP_CFG,
                "setup.py": "from setuptools import setup\n"
                "setup(install_requires=['x'])\n",
                "src/plug/__init__.py": "",
            },
        )


def test_the_version_file_a_build_would_write_is_written(tmp_path: Path) -> None:
    """setuptools_scm's write_to: packages import it, so a copy must have it."""
    project = read(
        tmp_path,
        {
            "pyproject.toml": SCM,
            "setup.cfg": SETUP_CFG,
            "src/plug/__init__.py": "from ._version import version as __version__\n",
        },
        url="https://github.com/o/r/archive/1.5.0.zip",
    )
    target = tmp_path / "site"
    si.install(project, target)
    assert (target / "plug" / "_version.py").is_file()
    sys.path.insert(0, str(target))
    sys.modules.pop("plug", None)
    try:
        assert importlib.import_module("plug").__version__ == "1.5.0"
        record = next(target.glob("*.dist-info/RECORD")).read_text()
        assert "plug/_version.py" in record
    finally:
        sys.path.remove(str(target))
        sys.modules.pop("plug", None)
        sys.modules.pop("plug._version", None)


HATCH_NAMESPACE = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "space-api"
dynamic = ["version"]

[tool.hatch.version]
path = "src/space/version/__init__.py"

[tool.hatch.build.targets.wheel]
packages = ["src/space"]
"""


def test_a_namespace_package_declared_to_hatch_is_found(tmp_path: Path) -> None:
    """``src/space`` has no ``__init__.py``, and the version is read from a file."""
    project = read(
        tmp_path,
        {
            "pyproject.toml": HATCH_NAMESPACE,
            "src/space/trace/__init__.py": "",
            "src/space/version/__init__.py": '__version__ = "1.2.3"\n',
        },
    )
    assert [p.name for p in project.packages] == ["space"]
    assert project.version == Version("1.2.3")


def test_a_namespace_package_in_src_is_found_without_being_declared(
    tmp_path: Path,
) -> None:
    """A folder in ``src`` with Python anywhere inside is a package."""
    pyproject = HATCH_NAMESPACE.replace('packages = ["src/space"]', "")
    project = read(
        tmp_path,
        {"pyproject.toml": pyproject, "src/space/trace/__init__.py": ""},
    )
    assert [p.name for p in project.packages] == ["space"]


def test_a_declared_package_outside_the_project_is_ignored(tmp_path: Path) -> None:
    """An archive can't aim the copy at something else."""
    pyproject = HATCH_NAMESPACE.replace('"src/space"]', '"../elsewhere"]', 1)
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "x.py").write_text("")
    project = read(
        tmp_path / "project",
        {"pyproject.toml": pyproject, "src/space/trace/__init__.py": ""},
    )
    assert [p.name for p in project.packages] == ["space"]


@pytest.mark.parametrize(
    ("config", "files", "expected"),
    [
        (
            '[tool.pdm]\nversion = { source = "file", path = "a/__init__.py" }\n',
            {"a/__init__.py": '__version__ = "0.27.3"\n'},
            "0.27.3",
        ),
        (
            '[tool.setuptools.dynamic]\nversion = { attr = "a.about.__version__" }\n',
            {"a/__init__.py": "", "a/about.py": "__version__ = '4.5'\n"},
            "4.5",
        ),
        (
            '[tool.setuptools.dynamic]\nversion = { file = "VERSION" }\n',
            {"a/__init__.py": "", "VERSION": "6.7\n"},
            "6.7",
        ),
    ],
)
def test_a_version_is_read_from_the_file_named_for_it(
    tmp_path: Path, config: str, files: dict, expected: str
) -> None:
    """Static text only: nothing is imported or run."""
    pyproject = (
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "setuptools.build_meta"\n'
        '[project]\nname = "a"\ndynamic = ["version"]\n' + config
    )
    project = read(tmp_path, {"pyproject.toml": pyproject, **files})
    assert project.version == Version(expected)


def test_flit_reads_the_version_from_the_module(tmp_path: Path) -> None:
    """Flit's own rule: ``__version__`` in the module named after the project."""
    pyproject = (
        '[build-system]\nrequires = ["flit_core"]\n'
        'build-backend = "flit_core.buildapi"\n'
        '[project]\nname = "a-b"\ndynamic = ["version"]\n'
    )
    files = {"pyproject.toml": pyproject, "src/a_b/__init__.py": '__version__ = "9"\n'}
    assert read(tmp_path, files).version == Version("9")


def test_setup_py_is_ignored_when_another_backend_builds(tmp_path: Path) -> None:
    """tomli has an optional mypyc setup.py that flit never runs."""
    pyproject = (
        '[build-system]\nrequires = ["flit_core"]\n'
        'build-backend = "flit_core.buildapi"\n'
        '[project]\nname = "a"\nversion = "1"\n'
    )
    files = {
        "pyproject.toml": pyproject,
        "setup.py": "from x import mypycify\nsetup(ext_modules=mypycify([]))\n",
        "src/a/__init__.py": "",
    }
    assert read(tmp_path, files).name == "a"


RUST = """
[build-system]
requires = ["maturin"]
build-backend = "maturin"

[project]
name = "fast"
version = "1"
"""


def test_a_compiled_build_is_named_before_looking_for_packages(tmp_path: Path) -> None:
    """orjson keeps its Python in pysrc/, and the reason should be the Rust."""
    with pytest.raises(si.SourceProblem, match="maturin"):
        read(tmp_path, {"pyproject.toml": RUST, "pysrc/fast/__init__.py": ""})


@pytest.mark.parametrize(
    ("extra", "file"),
    [
        ('[tool.poetry.build]\nscript = "build.py"\n', ""),
        ("[tool.pdm.build]\nrun-setuptools = true\n", ""),
        ("", "hatch_build.py"),
        ("", "pdm_build.py"),
    ],
)
def test_build_scripts_are_refused(tmp_path: Path, extra: str, file: str) -> None:
    """They generate or compile things that a copy wouldn't have."""
    files = {
        "pyproject.toml": (
            '[build-system]\nrequires = ["hatchling"]\n'
            'build-backend = "hatchling.build"\n'
            f'[project]\nname = "a"\nversion = "1"\n{extra}'
        ),
        "a/__init__.py": "",
    }
    if file:
        files[file] = ""
    with pytest.raises(si.SourceProblem, match="build"):
        read(tmp_path, files)


def test_a_github_archive_with_no_version_shows_its_commit(tmp_path: Path) -> None:
    """The zip's comment is the commit, which says more than ``0+unknown``."""
    pyproject = (
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "setuptools.build_meta"\n'
        '[project]\nname = "a"\ndynamic = ["version"]\n'
    )
    archive = tmp_path / "a.zip"
    archive.write_bytes(
        make_zip({"pyproject.toml": pyproject, "src/a/__init__.py": ""})
    )
    with zipfile.ZipFile(archive, "a") as zf:
        zf.comment = b"2247b35ea1c47c727d7a06e51fa280e12a863ff6"
    assert si.commit_of(archive) == "2247b35ea1c47c727d7a06e51fa280e12a863ff6"
    root = si.extract(archive, tmp_path / "unpacked")
    project = si.read_project(root, URL, "a", commit=si.commit_of(archive))
    assert project.version == Version("0+g2247b35")
    assert si.version_is_unknown(project.version)
    assert not si.version_is_unknown(Version("1.0+local"))


def test_purity_still_refuses_compiled_source_in_a_namespace(tmp_path: Path) -> None:
    """The new package forms are checked like any other."""
    files = {
        "pyproject.toml": HATCH_NAMESPACE,
        "src/space/trace/__init__.py": "",
        "src/space/trace/fast.c": "",
    }
    with pytest.raises(si.SourceProblem, match=r"fast\.c"):
        read(tmp_path, files)
