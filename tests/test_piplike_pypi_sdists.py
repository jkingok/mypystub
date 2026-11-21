"""A package with no usable wheel is built from its source distribution (#257)."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx2
import pytest
from packaging.tags import Tag
from packaging.version import Version

from mypystub import piplike
from mypystub.piplike import DependencyError, Link
from tests.support_sources import (
    ANY,
    install_fake_backend,
    make_zip,
    resolve,
    serve,
)

INDEX = "https://files.example.com"
PYPROJECT = (
    '[build-system]\nrequires = ["fakebackend"]\nbuild-backend = "fakebackend"\n'
    '[project]\nname = "{name}"\nversion = "{version}"\n'
)


class Finder:
    """An index with only what the test publishes: (name, version, filename)."""

    def __init__(self) -> None:
        self.files: list[tuple[str, str, str]] = []
        self.served: dict[str, bytes] = {}

    def add_sdist(self, name: str, version: str, extra: dict[str, str] | None = None):
        filename = f"{name}-{version}.zip"
        files = {
            "pyproject.toml": PYPROJECT.format(name=name, version=version),
            f"{name}/__init__.py": f"VERSION = '{version}'\n",
            **(extra or {}),
        }
        self.served[f"{INDEX}/{filename}"] = make_zip(files, top=f"{name}-{version}")
        self.files.append((name, version, filename))

    def add_wheel_name(self, name: str, version: str, tag: str) -> None:
        """A wheel the platform can't use (it is listed, never fetched)."""
        self.files.append((name, version, f"{name}-{version}-{tag}.whl"))

    def find_matches(self, name: str) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(name=n, version=v, link=Link(f"{INDEX}/{f}"))
            for n, v, f in self.files
            if n == name
        ]


def provider(
    tmp_path: Path, finder: Finder, **kwargs: Any
) -> piplike.PyPIWheelProvider:
    return piplike.PyPIWheelProvider(
        finder=finder,  # type: ignore[arg-type]
        cache_dir=tmp_path / "cache",
        system_packages=kwargs.pop("system", {}),
        http_client=httpx2.Client(transport=serve(finder.served)),
        supported_tags={Tag("py3", "none", "any")} | ANY,
        backend_installer=install_fake_backend,
        **kwargs,
    )


def test_a_package_with_only_a_source_distribution_is_built(tmp_path: Path) -> None:
    finder = Finder()
    finder.add_sdist("thing", "1.0")
    pins = resolve(provider(tmp_path, finder), "thing")
    assert str(pins["thing"].version) == "1.0" and pins["thing"].is_direct


def test_the_newest_version_that_fits_is_the_one_built(tmp_path: Path) -> None:
    finder = Finder()
    for version in ("1.0", "2.0", "3.0"):
        finder.add_sdist("thing", version)
    pins = resolve(provider(tmp_path, finder), "thing<3")
    assert str(pins["thing"].version) == "2.0"
    built = [u for u in finder.served if "3.0" in u]
    assert built  # published, but never downloaded: nothing asked for it


def test_a_wheel_is_preferred_and_nothing_is_built(tmp_path: Path) -> None:
    from tests.test_piplike import build_wheel

    finder = Finder()
    wheel = build_wheel(tmp_path, "thing", "1.0", None)
    finder.served[f"{INDEX}/{wheel.name}"] = wheel.read_bytes()
    finder.files.append(("thing", "1.0", wheel.name))
    finder.add_sdist("thing", "2.0")  # newer, but only as source
    pins = resolve(provider(tmp_path, finder), "thing")
    assert str(pins["thing"].version) == "1.0"
    assert not (tmp_path / "cache" / "built").exists()


def test_a_source_that_cannot_be_built_says_why(tmp_path: Path) -> None:
    finder = Finder()
    finder.add_sdist("thing", "1.0", {"ext.c": "int main(){}\n"})
    with pytest.raises(DependencyError, match="thing"):
        resolve(provider(tmp_path, finder), "thing")


def test_a_package_with_a_substitute_is_not_built(tmp_path: Path) -> None:
    """pyyaml has source, but pyyaml-pure is the answer where it has no wheel."""
    finder = Finder()
    finder.add_sdist("pyyaml", "6.0", {"ext.c": "int main(){}\n"})
    finder.add_sdist("pyyaml-pure", "6.0.3")
    pins = resolve(provider(tmp_path, finder), "pyyaml")
    assert pins["pyyaml"].name == "pyyaml-pure"


def test_python_magic_pure_installs_from_its_source_distribution(
    tmp_path: Path,
) -> None:
    """The case that prompted this: no wheel anywhere, and it is wanted by name."""
    finder = Finder()
    finder.add_sdist("python-magic-pure", "0.1.0")
    pins = resolve(provider(tmp_path, finder), "python-magic-pure")
    assert pins["python-magic-pure"].version == Version("0.1.0")
