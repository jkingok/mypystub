"""Packages installed from git record their commit, as pip does (#328 follow-up)."""

import asyncio
import io
import json
import zipfile
from pathlib import Path
from typing import Any

from mypystub import git_updates, piplike, source_installs
from tests.support_sources import make_zip, provider, resolve

SHA = "c0ffee" + "1" * 34
OLD = "badbad" + "2" * 34
API = "https://api.github.com/repos/o/thing/commits/{}"
PYPROJECT = (
    '[build-system]\nrequires = ["fakebackend"]\nbuild-backend = "fakebackend"\n'
    '[project]\nname = "thing"\ndynamic = ["version"]\n'
)
PROJECT = {"pyproject.toml": PYPROJECT, "thing/__init__.py": "VALUE = 1\n"}


def run(coro: Any) -> Any:
    """Run `coro` on a loop of its own, leaving the current loop alone."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_the_branch_s_commit_is_asked_for_built_and_recorded(tmp_path: Path) -> None:
    served = {
        API.format("HEAD"): SHA.encode(),
        f"https://github.com/o/thing/archive/{SHA}.zip": make_zip(PROJECT),
    }
    pins = resolve(provider(tmp_path, served), "thing @ git+https://github.com/o/thing")
    found = git_updates.source_from("thing", pins["thing"].direct_url)
    assert found == git_updates.GitSource("thing", "https://github.com/o/thing", SHA)
    assert str(pins["thing"].version) == f"0+g{SHA[:7]}"


def test_a_tag_still_names_the_version_and_is_recorded(tmp_path: Path) -> None:
    served = {
        API.format("v1.2"): SHA.encode(),
        f"https://github.com/o/thing/archive/{SHA}.zip": make_zip(PROJECT),
    }
    pins = resolve(
        provider(tmp_path, served), "thing @ git+https://github.com/o/thing@v1.2"
    )
    assert str(pins["thing"].version) == "1.2"
    data = json.loads(pins["thing"].direct_url)
    assert data["vcs_info"] == {
        "vcs": "git",
        "commit_id": SHA,
        "requested_revision": "v1.2",
    }


def zip_with_comment(comment: str) -> bytes:
    buffer = io.BytesIO(make_zip(PROJECT))
    with zipfile.ZipFile(buffer, "a") as archive:
        archive.comment = comment.encode()
    return buffer.getvalue()


def test_without_the_host_a_github_zip_s_own_commit_is_used(tmp_path: Path) -> None:
    served = {"https://github.com/o/thing/archive/HEAD.zip": zip_with_comment(SHA)}
    pins = resolve(provider(tmp_path, served), "thing @ git+https://github.com/o/thing")
    found = git_updates.source_from("thing", pins["thing"].direct_url)
    assert found is not None and found.commit == SHA


def test_a_commit_pin_is_not_looked_up(tmp_path: Path) -> None:
    served = {f"https://github.com/o/thing/archive/{SHA}.zip": make_zip(PROJECT)}
    pins = resolve(
        provider(tmp_path, served), f"thing @ git+https://github.com/o/thing@{SHA}"
    )
    found = git_updates.source_from("thing", pins["thing"].direct_url)
    assert found is not None and found.commit == SHA and found.pinned


def test_a_commit_that_starts_with_a_digit_is_not_a_version(tmp_path: Path) -> None:
    digits = "1234567" + "a" * 33
    hint = source_installs.version_hint(
        tmp_path, f"https://github.com/o/thing/archive/{digits}.zip", digits
    )
    assert hint == "0+g1234567"


def installed_direct_url(site: Path) -> dict[str, Any]:
    (info,) = site.glob("thing-*.dist-info")
    assert "direct_url.json" in (info / "RECORD").read_text()
    return json.loads((info / "direct_url.json").read_text())


def test_installing_writes_direct_url_json(tmp_path: Path) -> None:
    served = {
        API.format("HEAD"): SHA.encode(),
        f"https://github.com/o/thing/archive/{SHA}.zip": make_zip(PROJECT),
    }
    pins = resolve(provider(tmp_path, served), "thing @ git+https://github.com/o/thing")
    site = tmp_path / "site"
    site.mkdir()
    run(piplike.install_resolved(pins, site, tmp_path / "cache", True))
    assert installed_direct_url(site)["vcs_info"]["commit_id"] == SHA
    # Check for updates can now find it
    assert git_updates.git_sources([str(site)])["thing"].commit == SHA


def test_a_new_commit_is_installed_even_at_the_same_version(tmp_path: Path) -> None:
    """A static version doesn't change between commits; the recorded commit does."""
    static = dict(
        PROJECT,
        **{
            "pyproject.toml": PYPROJECT.replace(
                'dynamic = ["version"]', 'version = "1.0"'
            )
        },
    )
    site = tmp_path / "site"
    site.mkdir()
    for commit in (OLD, SHA):
        served = {
            API.format("HEAD"): commit.encode(),
            f"https://github.com/o/thing/archive/{commit}.zip": make_zip(static),
        }
        cache = tmp_path / commit
        p = provider(cache.parent, served)
        p.cache_dir = cache
        pins = resolve(p, "thing @ git+https://github.com/o/thing")
        run(piplike.install_resolved(pins, site, cache, True))
        assert installed_direct_url(site)["vcs_info"]["commit_id"] == commit
