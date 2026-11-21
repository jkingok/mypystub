"""scripts/check_public_deps.py: main depends on public repositories only."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "check_public_deps.py"

pytestmark = pytest.mark.skipif(
    not SCRIPT.exists(), reason="scripts/ is not bundled on device"
)


@pytest.fixture
def check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_public_deps", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "line",
    [
        '"togax-jkingok @ git+https://github.com/jkingok/togax-jkingok-internal@b"',
        'source = { git = "https://github.com/jkingok/togax-jkingok-internal?rev=x" }',
        "x @ git+ssh://git@github.com/jkingok/togax-jkingok-internal.git",
        "git@github.com:jkingok/togax-jkingok-internal.git",
        "https://gitlab.com/group/thing-internal",
    ],
)
def test_internal_repositories_are_found(check: ModuleType, line: str) -> None:
    assert check.internal_references(line)


@pytest.mark.parametrize(
    "line",
    [
        '"togax-jkingok @ git+https://github.com/jkingok/togax-jkingok@v0.1.0"',
        '"toga-core @ git+https://github.com/beeware/toga.git#subdirectory=core"',
        "internal-tools = '1.0'  # a package, not a repository",
        "https://github.com/someone/internal-docs",
    ],
)
def test_public_repositories_pass(check: ModuleType, line: str) -> None:
    assert not check.internal_references(line)


def test_problems_name_the_file_and_line(check: ModuleType, tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        'name = "x"\n"y @ git+https://github.com/o/y-internal@dev"\n'
    )
    assert check.problems(tmp_path, ["pyproject.toml", "missing.lock"]) == [
        "pyproject.toml:2: github.com/o/y-internal"
    ]


def test_this_branch_passes_or_explains(check: ModuleType) -> None:
    """Whatever the branch, the check runs over the real files."""
    assert isinstance(check.problems(), list)
