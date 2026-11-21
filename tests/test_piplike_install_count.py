"""install_resolved counts its steps: fetching and checking, then installing."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from packaging.version import Version

from mypystub import piplike
from tests.test_piplike_install_order import wheel_bytes


def candidate(name: str, **kwargs: Any) -> piplike.Candidate:
    return piplike.Candidate(
        name=name,
        version=Version("1.0"),
        link=piplike.Link(f"https://example.com/{name}-1.0-py3-none-any.whl"),
        identifier=name,
        **kwargs,
    )


def test_steps_are_counted_through_each_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def download(client: Any, url: str, path: Path) -> None:
        name = url.rsplit("/", 1)[1].split("-")[0]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(wheel_bytes(name, "py3-none-any"))

    monkeypatch.setattr(piplike, "download_wheel_async", download)
    mapping = {
        "a": candidate("a"),
        "b": candidate("b"),
        "sys": candidate("sys", is_system=True),  # bundled: not a step
    }
    target = tmp_path / "site"
    target.mkdir()
    counts: list[tuple[int, int]] = []
    installed = asyncio.run(
        piplike.install_resolved(
            mapping,
            target,
            tmp_path / "cache",
            True,
            on_count=lambda *c: counts.append(c),
        )
    )
    assert installed == 2
    # fetch a, b; then install a, b; then done
    assert counts == [(0, 2), (1, 2), (0, 2), (1, 2), (2, 2)]


def test_the_count_ends_with_nothing_left_even_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: Any, **kwargs: Any) -> Any:
        raise piplike.DependencyError("no")

    monkeypatch.setattr(piplike, "install_resolved", fail)
    monkeypatch.setattr(
        piplike, "get_package_inventory", lambda *a, **k: {}
    )  # nothing installed yet
    counts: list[tuple[int, int]] = []
    with pytest.raises(piplike.DependencyError):
        asyncio.run(
            piplike.resolve_and_install_async(
                [],
                tmp_path / "site",
                cache_dir=tmp_path / "cache",
                on_count=lambda *c: counts.append(c),
            )
        )
    assert counts[-1] == (0, 0)
