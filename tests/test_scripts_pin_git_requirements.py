"""Tests for scripts/pin_git_requirements.py, which pins git requirements."""

import importlib.util
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "pin_git_requirements.py"

pytestmark = pytest.mark.skipif(
    not SCRIPT.exists(), reason="scripts/ is not bundled on device"
)

TOGA = "https://github.com/beeware/toga.git"
SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER = "fedcba9876543210fedcba9876543210fedcba98"

PYPROJECT = f"""\
[tool.briefcase.app.demo.iOS]
requires = [
    "toga-core @ git+{TOGA}#subdirectory=core",  # newest Toga
    "toga-iOS @ git+{TOGA}#subdirectory=iOS",
    "other @ git+https://example.com/other.git@{OTHER}",
    "plain>=1.0",
]

[tool.briefcase.app.demo.android]
requires = ['travertino @ git+{TOGA}#subdirectory=travertino']
"""


def load():
    """Import the script as a module."""
    spec = importlib.util.spec_from_file_location("pin_git_requirements", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_finds_each_unpinned_repository_once() -> None:
    """Toga appears three times but is one repository; pinned ones are skipped."""
    assert load().unpinned_urls(PYPROJECT) == [TOGA]


def test_pin_adds_the_commit_before_the_fragment() -> None:
    """Every Toga URL gets the commit; nothing else in the file changes."""
    pinned = load().pin(PYPROJECT, {TOGA: SHA})
    assert pinned == PYPROJECT.replace(f"{TOGA}#", f"{TOGA}@{SHA}#")
    requires = tomllib.loads(pinned)["tool"]["briefcase"]["app"]["demo"]
    assert (
        f"toga-core @ git+{TOGA}@{SHA}#subdirectory=core" in requires["iOS"]["requires"]
    )
    assert requires["android"]["requires"] == [
        f"travertino @ git+{TOGA}@{SHA}#subdirectory=travertino"
    ]


def test_pinning_twice_changes_nothing() -> None:
    """A pinned file has nothing left to pin."""
    module = load()
    pinned = module.pin(PYPROJECT, {TOGA: SHA})
    assert module.unpinned_urls(pinned) == []
    assert module.pin(pinned, {TOGA: OTHER}) == pinned


def test_url_without_fragment_is_pinned() -> None:
    """A requirement for the repository's root has no #subdirectory."""
    text = f'requires = ["pkg @ git+{TOGA}"]\n'
    assert load().pin(text, {TOGA: SHA}) == f'requires = ["pkg @ git+{TOGA}@{SHA}"]\n'


def test_pin_file_writes_the_commits(tmp_path: Path) -> None:
    """pin_file asks once per repository and rewrites the file."""
    path = tmp_path / "pyproject.toml"
    path.write_text(PYPROJECT, encoding="utf-8")
    asked = []

    def resolve(url: str) -> str:
        asked.append(url)
        return SHA

    assert load().pin_file(path, resolve) == {TOGA: SHA}
    assert asked == [TOGA]
    assert path.read_text(encoding="utf-8").count(f"{TOGA}@{SHA}#") == 3


def test_head_commit_rejects_a_reply_without_a_commit(monkeypatch) -> None:
    """An empty answer from git is an error, not an empty pin."""
    module = load()

    class Done:
        stdout = ""

    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: Done())
    with pytest.raises(ValueError, match="no commit"):
        module.head_commit(TOGA)


def test_head_commit_reads_ls_remote(monkeypatch) -> None:
    """The commit is the first field of git ls-remote's HEAD line."""
    module = load()

    class Done:
        stdout = f"{SHA}\tHEAD\n"

    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: Done())
    assert module.head_commit(TOGA) == SHA
