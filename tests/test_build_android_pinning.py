"""build_android.py pins Toga's git requirements for a build, then restores them."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "build_android.py"

pytestmark = pytest.mark.skipif(
    not SCRIPT.exists(), reason="scripts/ is not bundled on device"
)

UNPINNED = b'"toga-core @ git+https://github.com/beeware/toga.git#subdirectory=core"\n'


def load() -> ModuleType:
    """Import the script as a module."""
    spec = importlib.util.spec_from_file_location("build_android_pinning", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_pin(path: Path) -> None:
    """Stand in for pin_git_requirements.py without asking git."""
    path.write_bytes(path.read_bytes().replace(b".git#", b".git@" + b"a" * 40 + b"#"))


def test_pinned_during_build_and_restored_after(tmp_path: Path) -> None:
    """Briefcase sees the commit; the file is exactly as it was afterwards."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_bytes(UNPINNED)
    with load().pinned(pyproject, pin=fake_pin):
        assert b"toga.git@" + b"a" * 40 in pyproject.read_bytes()
    assert pyproject.read_bytes() == UNPINNED


def test_restored_when_the_build_fails(tmp_path: Path) -> None:
    """A failed Briefcase step doesn't leave the pin behind."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_bytes(UNPINNED)
    with pytest.raises(RuntimeError), load().pinned(pyproject, pin=fake_pin):
        raise RuntimeError("briefcase failed")
    assert pyproject.read_bytes() == UNPINNED


def test_restored_when_pinning_fails(tmp_path: Path) -> None:
    """git being unreachable leaves pyproject.toml untouched."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_bytes(UNPINNED)

    def broken(path: Path) -> None:
        path.write_bytes(b"half-written")
        raise OSError("no network")

    with pytest.raises(OSError), load().pinned(pyproject, pin=broken):
        pass
    assert pyproject.read_bytes() == UNPINNED
