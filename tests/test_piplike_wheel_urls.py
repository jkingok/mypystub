"""Requirements that name a wheel by URL (#171): ``foo @ https://.../foo-1.0-....whl``."""

import asyncio
import hashlib
import sys
import zipfile
from pathlib import Path
from typing import Any, cast

import httpx2
import pytest
import resolvelib
from packaging.requirements import Requirement
from packaging.tags import Tag
from packaging.version import Version

from mypystub import direct_refs, piplike

HOST = "https://files.example"
ANY = {Tag("py3", "none", "any")}


def build(directory: Path, name: str, version: str, requires: tuple[str, ...] = ()):
    """A tiny wheel for `name`, returned as (path, bytes)."""
    path = directory / f"{name}-{version}-py3-none-any.whl"
    meta = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    meta += "".join(f"Requires-Dist: {r}\n" for r in requires)
    with zipfile.ZipFile(path, "w") as wheel:
        wheel.writestr(f"{name}.py", f"VALUE = '{name} {version}'\n")
        wheel.writestr(f"{name}-{version}.dist-info/METADATA", meta)
        wheel.writestr(
            f"{name}-{version}.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        wheel.writestr(f"{name}-{version}.dist-info/RECORD", "")
    return path, path.read_bytes()


def provider(
    tmp_path: Path, served: dict[str, bytes], **kwargs: Any
) -> piplike.PyPIWheelProvider:
    """A provider whose HTTP client serves `served` (URL -> bytes); no index."""
    requests: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        url = str(request.url)
        requests.append(url)
        if url in served:
            return httpx2.Response(200, content=served[url])
        return httpx2.Response(404)

    result = piplike.PyPIWheelProvider(
        finder=cast(Any, None),
        cache_dir=tmp_path / "cache",
        system_packages=kwargs.pop("system", {}),
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
        supported_tags=kwargs.pop("tags", ANY),
        **kwargs,
    )
    result.requests = requests  # type: ignore[attr-defined]
    return result


def resolve(p: piplike.PyPIWheelProvider, *requirements: str) -> dict[str, Any]:
    """Resolve, returning the pinned candidates by name."""
    resolver = resolvelib.Resolver(p, resolvelib.BaseReporter())
    return dict(resolver.resolve([Requirement(r) for r in requirements]).mapping)


def test_a_wheel_url_is_that_wheel(tmp_path: Path) -> None:
    """The candidate is the wheel at the URL, with the version in its name."""
    _, data = build(tmp_path, "foo", "1.2")
    url = f"{HOST}/foo-1.2-py3-none-any.whl"
    pinned = resolve(provider(tmp_path, {url: data}), f"foo @ {url}")
    candidate = pinned["foo"]
    assert candidate.is_direct and candidate.version == Version("1.2")
    assert candidate.link.url == url


def test_its_own_dependencies_are_resolved(tmp_path: Path) -> None:
    """The wheel's METADATA is read, and what it requires joins the resolution."""
    _, data = build(tmp_path, "foo", "1.0", ("bar>=1",))
    url = f"{HOST}/foo-1.0-py3-none-any.whl"
    p = provider(tmp_path, {url: data}, system={"bar": Version("2.0")})
    pinned = resolve(p, f"foo @ {url}")
    assert set(pinned) == {"foo", "bar"} and pinned["bar"].is_system


def test_the_download_is_cached_by_url(tmp_path: Path) -> None:
    """Resolving twice fetches the file once; same-named files don't clash."""
    _, data = build(tmp_path, "foo", "1.0")
    url = f"{HOST}/foo-1.0-py3-none-any.whl"
    p = provider(tmp_path, {url: data})
    resolve(p, f"foo @ {url}")
    p2 = provider(tmp_path, {url: data})
    resolve(p2, f"foo @ {url}")
    assert p.requests == [url] and p2.requests == []  # type: ignore[attr-defined]
    other = f"{HOST}/other/foo-1.0-py3-none-any.whl"
    assert direct_refs.cache_path(tmp_path, url) != direct_refs.cache_path(
        tmp_path, other
    )


def test_a_matching_sha256_is_accepted_and_a_wrong_one_refused(
    tmp_path: Path,
) -> None:
    """``#sha256=`` is checked against the downloaded file."""
    _, data = build(tmp_path, "foo", "1.0")
    url = f"{HOST}/foo-1.0-py3-none-any.whl"
    good = hashlib.sha256(data).hexdigest()
    resolve(provider(tmp_path, {url: data}), f"foo @ {url}#sha256={good}")
    with pytest.raises(piplike.DependencyError, match="sha256"):
        resolve(provider(tmp_path / "x", {url: data}), f"foo @ {url}#sha256={'0' * 64}")


@pytest.mark.parametrize(
    ("requirement", "fragment"),
    [
        ("foo @ {h}/bar-1.0-py3-none-any.whl", "wheel for bar, not foo"),
        ("foo @ {h}/foo-1.0-cp99-cp99-win_amd64.whl", "isn't built for this device"),
        ("foo @ {h}/foo.whl", "isn't a valid wheel file name"),
    ],
)
def test_a_wheel_that_does_not_fit_is_refused(
    tmp_path: Path, requirement: str, fragment: str
) -> None:
    """Wrong project, wrong platform or a bad file name each say so."""
    with pytest.raises(piplike.DependencyError, match=fragment):
        resolve(provider(tmp_path, {}), requirement.format(h=HOST))


def test_a_bundled_package_cannot_be_replaced_by_a_url(tmp_path: Path) -> None:
    """A second copy would shadow the app's own, as for any other requirement."""
    p = provider(tmp_path, {}, system={"foo": Version("1.0")})
    with pytest.raises(piplike.DependencyError, match="bundled"):
        resolve(p, f"foo @ {HOST}/foo-1.0-py3-none-any.whl")


def test_two_different_urls_for_one_name_are_refused(tmp_path: Path) -> None:
    """The requirement set contradicts itself."""
    p = provider(tmp_path, {})
    with pytest.raises(piplike.DependencyError, match="more than one URL"):
        resolve(
            p,
            f"foo @ {HOST}/a/foo-1.0-py3-none-any.whl",
            f"foo @ {HOST}/b/foo-1.0-py3-none-any.whl",
        )


def test_a_failed_download_names_the_url(tmp_path: Path) -> None:
    """A 404 is a clear DependencyError, not an empty wheel."""
    with pytest.raises(piplike.DependencyError, match="Couldn't download"):
        resolve(provider(tmp_path, {}), f"foo @ {HOST}/foo-1.0-py3-none-any.whl")


def test_install_unpacks_the_wheel_so_it_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end: resolve, download, unpack, and import the module."""
    _, data = build(tmp_path, "wheelurlmod", "3.1")
    url = f"{HOST}/wheelurlmod-3.1-py3-none-any.whl"

    def handler(request: httpx2.Request) -> httpx2.Response:
        if str(request.url) == url:
            return httpx2.Response(200, content=data)
        return httpx2.Response(404)

    transport = httpx2.MockTransport(handler)
    real_client, real_async = httpx2.Client, httpx2.AsyncClient
    monkeypatch.setattr(
        piplike.httpx2, "Client", lambda **kw: real_client(transport=transport, **kw)
    )
    monkeypatch.setattr(
        piplike.httpx2,
        "AsyncClient",
        lambda **kw: real_async(transport=transport, **kw),
    )
    target = tmp_path / "site"
    asyncio.run(
        piplike.resolve_and_install_async(
            [f"wheelurlmod @ {url}"],
            target,
            cache_dir=tmp_path / "cache",
            use_system=False,
        )
    )
    monkeypatch.syspath_prepend(str(target))
    monkeypatch.delitem(sys.modules, "wheelurlmod", raising=False)
    import importlib

    assert importlib.import_module("wheelurlmod").VALUE == "wheelurlmod 3.1"
