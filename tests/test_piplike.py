"""Tests for the pip emulation in mypystub.piplike.

No test touches the network: the package index is a fake PackageFinder and HTTP
is served by an httpx2 MockTransport from wheels built in tmp_path.
"""

import asyncio
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import httpx2
import pytest
import resolvelib
from packaging.requirements import Requirement
from packaging.version import Version
from unearth.link import Link

from mypystub import piplike
from mypystub.piplike import Candidate, PyPIWheelProvider

INDEX = "https://files.example.test/packages"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def metadata_text(name: str, version: str, requires: list[str]) -> str:
    """Return a minimal core metadata file."""
    lines = ["Metadata-Version: 2.1", f"Name: {name}", f"Version: {version}"]
    lines += [f"Requires-Dist: {r}" for r in requires]
    return "\n".join(lines) + "\n"


def build_wheel(
    directory: Path, name: str, version: str, requires: list[str] | None = None
) -> Path:
    """Build a pure-Python wheel containing a single module named after `name`."""
    module = name.replace("-", "_")
    dist_info = f"{module}-{version}.dist-info"
    files = {
        f"{module}.py": f"VERSION = {version!r}\n",
        f"{dist_info}/METADATA": metadata_text(name, version, requires or []),
        f"{dist_info}/WHEEL": (
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\n"
            "Tag: py3-none-any\n"
        ),
    }
    record = "".join(f"{path},,\n" for path in files) + f"{dist_info}/RECORD,,\n"
    files[f"{dist_info}/RECORD"] = record

    wheel_path = directory / f"{module}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return wheel_path


@dataclass
class FakeIndex:
    """A fake package index serving wheels built on the fly."""

    directory: Path
    # canonical name -> list of (version, filename, requires)
    packages: dict[str, list[tuple[str, str, list[str]]]] = field(default_factory=dict)
    requests: list[str] = field(default_factory=list)
    fail_downloads: bool = False

    def add(
        self,
        name: str,
        version: str,
        requires: list[str] | None = None,
        filename: str | None = None,
    ) -> None:
        """Publish a version of `name`, optionally under a custom filename."""
        wheel = build_wheel(self.directory, name, version, requires)
        if filename:
            wheel = wheel.rename(self.directory / filename)
        self.packages.setdefault(name, []).append((version, wheel.name, requires or []))

    # PackageFinder interface used by PyPIWheelProvider
    def find_matches(self, name: str) -> list[SimpleNamespace]:
        """Return unearth-like matches for `name`, newest first."""
        return [
            SimpleNamespace(
                name=name, version=version, link=Link(f"{INDEX}/{filename}")
            )
            for version, filename, _ in sorted(
                self.packages.get(name, []), key=lambda p: Version(p[0]), reverse=True
            )
        ]

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        """Serve wheel files and their PEP 658 .metadata files."""
        url = str(request.url)
        self.requests.append(url)
        filename = url.rsplit("/", 1)[-1]
        for name, versions in self.packages.items():
            for version, wheel_name, requires in versions:
                if filename == wheel_name:
                    if self.fail_downloads:
                        return httpx2.Response(500)
                    return httpx2.Response(
                        200, content=(self.directory / wheel_name).read_bytes()
                    )
                if filename == f"{wheel_name}.metadata":
                    return httpx2.Response(
                        200, text=metadata_text(name, version, requires)
                    )
        return httpx2.Response(404)


@pytest.fixture
def index(tmp_path: Path) -> FakeIndex:
    """An empty fake package index."""
    directory = tmp_path / "index"
    directory.mkdir()
    return FakeIndex(directory)


def make_provider(
    index: FakeIndex,
    tmp_path: Path,
    system: dict[str, str] | None = None,
    **kwargs: object,
) -> PyPIWheelProvider:
    """Build a provider wired to the fake index."""
    client = httpx2.Client(transport=httpx2.MockTransport(index.handler))
    return PyPIWheelProvider(
        finder=index,  # pyright: ignore[reportArgumentType]
        cache_dir=tmp_path / "cache",
        system_packages={k: Version(v) for k, v in (system or {}).items()},
        http_client=client,
        **kwargs,  # pyright: ignore[reportArgumentType]
    )


def resolve(provider: PyPIWheelProvider, *requirements: str) -> dict[str, Candidate]:
    """Resolve requirements and return the pinned candidates by name."""
    resolver = resolvelib.Resolver(provider, resolvelib.BaseReporter())
    result = resolver.resolve([Requirement(r) for r in requirements])
    return dict(result.mapping)


def find(
    provider: PyPIWheelProvider,
    requirement: str,
    excluded: list[Candidate] | None = None,
) -> list[Candidate]:
    """Call find_matches the way resolvelib does, with iterator values."""
    req = Requirement(requirement)
    name = provider.identify(req)
    return provider.find_matches(
        name, {name: iter([req])}, {name: iter(excluded or [])}
    )


@pytest.fixture
def patched_network(monkeypatch: pytest.MonkeyPatch, index: FakeIndex) -> FakeIndex:
    """Route resolve_and_install_async's finder and HTTP clients to the fake index."""
    transport = httpx2.MockTransport(index.handler)
    real_client, real_async_client = httpx2.Client, httpx2.AsyncClient
    monkeypatch.setattr(piplike, "PackageFinder", lambda **_: index)
    monkeypatch.setattr(
        piplike.httpx2, "Client", lambda **kw: real_client(transport=transport, **kw)
    )
    monkeypatch.setattr(
        piplike.httpx2,
        "AsyncClient",
        lambda **kw: real_async_client(transport=transport, **kw),
    )
    return index


# ---------------------------------------------------------------------------
# Candidate
# ---------------------------------------------------------------------------


def test_candidate_canonicalises_name() -> None:
    """Names are normalised so lookups match regardless of spelling."""
    assert Candidate(name="My_Package", version=Version("1.0")).name == "my-package"


def test_candidate_str_shows_extras_and_source() -> None:
    """The string form is used in resolver progress output."""
    cand = Candidate(
        name="pkg",
        version=Version("2.0"),
        is_system=True,
        requested_extras=frozenset({"b", "a"}),
    )
    assert str(cand) == "pkg[a,b] 2.0 (system)"


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


def test_identify_applies_default_pyyaml_substitution(
    index: FakeIndex, tmp_path: Path
) -> None:
    """pyyaml is swapped for the pure-Python build by default."""
    provider = make_provider(index, tmp_path)
    assert provider.identify(Requirement("PyYAML>=6")) == "pyyaml-pure"
    assert provider.identify(Requirement("Other_Pkg")) == "other-pkg"


def test_find_matches_prefers_system_then_newest(
    index: FakeIndex, tmp_path: Path
) -> None:
    """A satisfying system package comes first, then PyPI versions newest first."""
    index.add("pkg", "1.0")
    index.add("pkg", "2.0")
    provider = make_provider(index, tmp_path, system={"pkg": "1.5"})
    matches = find(provider, "pkg")
    assert [(str(c.version), c.is_system) for c in matches] == [
        ("1.5", True),
        ("2.0", False),
        ("1.0", False),
    ]


def test_find_matches_skips_system_when_disabled(
    index: FakeIndex, tmp_path: Path
) -> None:
    """use_system=False ignores the bundled packages."""
    index.add("pkg", "1.0")
    provider = make_provider(index, tmp_path, system={"pkg": "1.5"}, use_system=False)
    matches = find(provider, "pkg")
    assert [c.is_system for c in matches] == [False]


def test_find_matches_applies_specifier(index: FakeIndex, tmp_path: Path) -> None:
    """Candidates outside the requested specifier are dropped, system included."""
    index.add("pkg", "1.0")
    index.add("pkg", "2.0")
    provider = make_provider(index, tmp_path, system={"pkg": "3.0"})
    matches = find(provider, "pkg<2")
    assert [str(c.version) for c in matches] == ["1.0"]


def test_find_matches_rejects_iphoneos_wheels(index: FakeIndex, tmp_path: Path) -> None:
    """Device-only binary wheels are skipped, simulator and pure wheels are kept."""
    index.add("pkg", "1.0")
    index.add("pkg", "2.0", filename="pkg-2.0-cp315-cp315-ios_13_0_arm64_iphoneos.whl")
    provider = make_provider(index, tmp_path)
    matches = find(provider, "pkg")
    assert [str(c.version) for c in matches] == ["1.0"]


def test_find_matches_respects_incompatibilities_and_limit(
    index: FakeIndex, tmp_path: Path
) -> None:
    """Known-bad candidates are excluded and the list is capped."""
    for minor in range(5):
        index.add("pkg", f"1.{minor}")
    provider = make_provider(index, tmp_path, max_candidates=2)
    newest = find(provider, "pkg")[0]
    assert str(newest.version) == "1.4"
    matches = find(provider, "pkg", excluded=[newest])
    assert [str(c.version) for c in matches] == ["1.3", "1.2"]


def test_parse_metadata_requirements_filters_extras(
    index: FakeIndex, tmp_path: Path
) -> None:
    """Only base dependencies and requested extras are kept."""
    provider = make_provider(index, tmp_path)
    text = metadata_text(
        "pkg",
        "1.0",
        ["base", 'socks ; extra == "socks"', 'testing ; extra == "test"'],
    )
    reqs = provider._parse_metadata_requirements(text, frozenset({"socks"}))
    assert [r.name for r in reqs] == ["base", "socks"]


def test_parse_metadata_requirements_substitutes_names(
    index: FakeIndex, tmp_path: Path
) -> None:
    """Substituted packages keep their version specifier."""
    provider = make_provider(index, tmp_path)
    reqs = provider._parse_metadata_requirements(
        "Requires-Dist: PyYAML>=6.0\n", frozenset()
    )
    assert [str(r) for r in reqs] == ["pyyaml-pure>=6.0"]


def test_fetch_metadata_handles_missing_and_errors(
    index: FakeIndex, tmp_path: Path
) -> None:
    """A 404 or transport error yields empty metadata rather than raising."""
    provider = make_provider(index, tmp_path)
    missing = Candidate(
        name="ghost", version=Version("1.0"), link=Link(f"{INDEX}/ghost.whl")
    )
    assert provider._fetch_candidate_metadata(missing) == ""
    assert provider._fetch_candidate_metadata(Candidate("x", Version("1"))) == ""

    def boom(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("offline", request=request)

    provider.http_client = httpx2.Client(transport=httpx2.MockTransport(boom))
    assert provider._fetch_candidate_metadata(missing) == ""


def test_get_dependencies_is_cached(index: FakeIndex, tmp_path: Path) -> None:
    """Metadata is fetched once per candidate."""
    index.add("pkg", "1.0", requires=["dep"])
    provider = make_provider(index, tmp_path)
    (cand,) = find(provider, "pkg")
    assert [r.name for r in provider.get_dependencies(cand)] == ["dep"]
    assert [r.name for r in provider.get_dependencies(cand)] == ["dep"]
    assert sum(url.endswith(".metadata") for url in index.requests) == 1


def test_system_dependencies_come_from_installed_metadata(
    index: FakeIndex, tmp_path: Path
) -> None:
    """A system candidate's dependencies are read from importlib.metadata."""
    provider = make_provider(index, tmp_path)
    # httpx2 is installed alongside the app and depends on anyio.
    cand = Candidate(name="httpx2", version=Version("0"), is_system=True)
    assert "anyio" in [r.name for r in provider.get_dependencies(cand)]
    ghost = Candidate(name="not-installed-pkg", version=Version("0"), is_system=True)
    assert provider.get_dependencies(ghost) == []


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def test_resolves_transitive_dependencies(index: FakeIndex, tmp_path: Path) -> None:
    """Dependencies are followed and the newest compatible versions pinned."""
    index.add("app", "1.0", requires=["lib>=2"])
    index.add("lib", "1.0")
    index.add("lib", "2.0")
    index.add("lib", "2.1")
    pins = resolve(make_provider(index, tmp_path), "app")
    assert {k: str(v.version) for k, v in pins.items()} == {"app": "1.0", "lib": "2.1"}


def test_resolution_uses_system_package(index: FakeIndex, tmp_path: Path) -> None:
    """A bundled package that satisfies the requirement wins over PyPI."""
    index.add("app", "1.0", requires=["lib"])
    index.add("lib", "9.0")
    pins = resolve(make_provider(index, tmp_path, system={"lib": "1.0"}), "app")
    assert pins["lib"].is_system


def test_resolution_fails_for_unknown_package(index: FakeIndex, tmp_path: Path) -> None:
    """A package that is not on the index cannot be resolved."""
    with pytest.raises(resolvelib.ResolutionImpossible):
        resolve(make_provider(index, tmp_path), "does-not-exist")


# ---------------------------------------------------------------------------
# Installing and removing
# ---------------------------------------------------------------------------


def test_unpack_inventory_and_remove(index: FakeIndex, tmp_path: Path) -> None:
    """A wheel unpacks into the target, shows in the inventory, and is removable."""
    target = tmp_path / "site"
    target.mkdir()
    wheel = build_wheel(index.directory, "demo-pkg", "1.2")
    piplike.unpack_wheel(wheel, target)

    assert (target / "demo_pkg.py").exists()
    assert piplike.get_package_inventory(target) == {"demo-pkg": "1.2"}
    dist = piplike.get_installed_distribution(target, "Demo_Pkg")
    assert dist is not None and dist.version == "1.2"

    piplike.remove_installed_package(target, "demo-pkg")
    assert not (target / "demo_pkg.py").exists()
    assert piplike.get_installed_distribution(target, "demo-pkg") is None
    assert piplike.get_package_inventory(target) == {}


def test_inventory_and_lookup_of_missing_target(tmp_path: Path) -> None:
    """A target directory that does not exist is treated as empty."""
    missing = tmp_path / "nope"
    assert piplike.get_package_inventory(missing) == {}
    assert piplike.get_installed_distribution(missing, "pkg") is None
    piplike.remove_installed_package(missing, "pkg")  # no error


def test_system_inventory_includes_app_dependencies() -> None:
    """With no target, the running interpreter's packages are listed."""
    assert "resolvelib" in piplike.get_package_inventory(None)


def test_resolve_and_install_async_installs_tree(
    patched_network: FakeIndex, tmp_path: Path
) -> None:
    """The full async path downloads and unpacks every non-system pin."""
    patched_network.add("app", "1.0", requires=["lib"])
    patched_network.add("lib", "2.0")
    target = tmp_path / "site"

    asyncio.run(piplike.resolve_and_install_async(["app"], target, use_system=False))

    assert piplike.get_package_inventory(target) == {"app": "1.0", "lib": "2.0"}


def test_resolve_and_install_async_upgrades_and_skips(
    patched_network: FakeIndex, tmp_path: Path
) -> None:
    """Installed matching versions are skipped; older ones are replaced."""
    target = tmp_path / "site"
    cache = tmp_path / "cache"
    patched_network.add("lib", "1.0")
    asyncio.run(
        piplike.resolve_and_install_async(
            ["lib"], target, cache_dir=cache, use_system=False
        )
    )
    downloads = [u for u in patched_network.requests if u.endswith(".whl")]
    assert len(downloads) == 1

    # Same version again: nothing new is downloaded (wheel is cached anyway).
    asyncio.run(
        piplike.resolve_and_install_async(
            ["lib"], target, cache_dir=cache, use_system=False
        )
    )
    assert piplike.get_package_inventory(target) == {"lib": "1.0"}

    patched_network.add("lib", "2.0")
    asyncio.run(
        piplike.resolve_and_install_async(
            ["lib"], target, cache_dir=cache, use_system=False
        )
    )
    assert piplike.get_package_inventory(target) == {"lib": "2.0"}
    assert (target / "lib.py").read_text() == "VERSION = '2.0'\n"


def test_resolve_and_install_async_skips_system_packages(
    patched_network: FakeIndex, tmp_path: Path
) -> None:
    """A requirement already bundled with the app installs nothing."""
    target = tmp_path / "site"
    asyncio.run(piplike.resolve_and_install_async(["resolvelib"], target))
    assert piplike.get_package_inventory(target) == {}
    assert not [u for u in patched_network.requests if u.endswith(".whl")]


def test_resolve_and_install_async_wraps_resolution_errors(
    patched_network: FakeIndex, tmp_path: Path
) -> None:
    """Unresolvable requirements surface as DependencyError for the UI."""
    with pytest.raises(piplike.DependencyError, match="resolution failed"):
        asyncio.run(
            piplike.resolve_and_install_async(
                ["does-not-exist"], tmp_path / "site", use_system=False
            )
        )


def test_resolve_and_install_async_wraps_download_errors(
    patched_network: FakeIndex, tmp_path: Path
) -> None:
    """A failed wheel download surfaces as DependencyError."""
    patched_network.add("lib", "1.0")
    patched_network.fail_downloads = True
    with pytest.raises(piplike.DependencyError, match="download failed"):
        asyncio.run(
            piplike.resolve_and_install_async(
                ["lib"], tmp_path / "site", use_system=False
            )
        )
