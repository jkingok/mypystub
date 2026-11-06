"""A URL requirement must be refused, not quietly installed from PyPI (#169)."""

from pathlib import Path
from typing import Any, cast

import pytest
import resolvelib
from packaging.requirements import Requirement

from mypystub import piplike


def resolve(text: str, tmp_path: Path) -> Any:
    """Resolve one requirement with a provider that has no index to ask."""
    provider = piplike.PyPIWheelProvider(
        finder=cast(Any, None),
        cache_dir=tmp_path,
        system_packages={},
        http_client=cast(Any, None),
    )
    resolver = resolvelib.Resolver(provider, resolvelib.BaseReporter())
    return resolver.resolve([Requirement(text)])


@pytest.mark.parametrize(
    "text",
    [
        "foo @ git+https://gitlab.com/o/r.git@v1",
        "foo @ git+ssh://git@github.com/o/r.git",
    ],
)
def test_url_requirement_raises_dependency_error(text: str, tmp_path: Path) -> None:
    """The resolver refuses before it looks for the name anywhere."""
    with pytest.raises(piplike.DependencyError, match="Can't install"):
        resolve(text, tmp_path)


def test_bundled_names_are_not_an_exception(tmp_path: Path) -> None:
    """Even a name the app bundles can't be redirected with a URL."""
    provider = piplike.PyPIWheelProvider(
        finder=cast(Any, None),
        cache_dir=tmp_path,
        system_packages={"foo": piplike.Version("1.0")},
        http_client=cast(Any, None),
    )
    resolver = resolvelib.Resolver(provider, resolvelib.BaseReporter())
    with pytest.raises(piplike.DependencyError):
        resolver.resolve([Requirement("foo @ git+ssh://git@github.com/o/r.git")])
