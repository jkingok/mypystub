"""python-magic is satisfied by the bundled python-magic-pure (#333)."""

from pathlib import Path

from packaging.version import Version

from mypystub.package_aliases import ALIASES, Alias
from tests.support_sources import provider, resolve


def test_python_magic_is_a_bundled_alias_not_a_runtime_substitute() -> None:
    """The real one needs libmagic; the pure one has no wheel to install."""
    assert ALIASES["python-magic"] == Alias("bundled", "python-magic-pure")


def test_a_script_needing_python_magic_installs_nothing(tmp_path: Path) -> None:
    p = provider(
        tmp_path,
        {},  # nothing can be downloaded
        system={"python-magic-pure": Version("0.1.0")},
    )
    pins = resolve(p, "python-magic>=0.4")
    assert pins["python-magic"].is_system
    assert str(pins["python-magic"].version) == "0.1.0"
