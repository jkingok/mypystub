"""Tests for the Setup view's cache, update and health logic (#77)."""

import json
from pathlib import Path

import httpx2
import pytest
from packaging.version import Version

from mypystub import maintenance as m


def client_for(routes: dict[str, object]) -> httpx2.Client:
    """An HTTP client answering JSON for known URLs and 404 for anything else."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        url = str(request.url)
        if url in routes:
            return httpx2.Response(200, text=json.dumps(routes[url]))
        return httpx2.Response(404)

    return httpx2.Client(transport=httpx2.MockTransport(handler))


def offline_client() -> httpx2.Client:
    """An HTTP client with no network."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("offline", request=request)

    return httpx2.Client(transport=httpx2.MockTransport(handler))


def release(name: str, pre: bool = False) -> dict[str, object]:
    """One entry of python.org's downloads API, with the fields we read."""
    return {"name": name, "pre_release": pre, "is_published": True}


def pypi(version: str) -> dict[str, object]:
    """A minimal PyPI JSON API response."""
    return {"info": {"version": version}}


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def test_dir_size_and_wipe(tmp_path: Path) -> None:
    """Sizes add up recursively; wiping removes the folder; both tolerate absence."""
    site = tmp_path / "site_packages"
    (site / "pkg").mkdir(parents=True)
    (site / "pkg" / "a.py").write_bytes(b"x" * 1000)
    (site / "b.txt").write_bytes(b"y" * 24)
    assert m.dir_size(site) == 1024
    m.wipe(site)
    assert not site.exists()
    assert m.dir_size(site) == 0
    m.wipe(site)  # already gone: no error


@pytest.mark.parametrize(
    ("size", "text"),
    [(0, "0 B"), (999, "999 B"), (1536, "1.5 KB"), (3 * 1024**2, "3.0 MB")],
)
def test_human_size(size: int, text: str) -> None:
    """Sizes read naturally."""
    assert m.human_size(size) == text


# ---------------------------------------------------------------------------
# Python releases (python.org)
# ---------------------------------------------------------------------------

RELEASES = [
    release("Python 3.15.0"),
    release("Python 3.15.2"),
    release("Python 3.15.1"),
    release("Python 3.14.9"),
    release("Python 3.16.0a3", pre=True),
    release("Python 3.16.0b1", pre=True),
    release("Python install manager 25.0"),  # not a CPython release name
]


def test_python_status_dot_release_and_next_prerelease() -> None:
    """Newest dot release on our branch, and the next version (a pre-release)."""
    status = m.python_status(RELEASES, "3.15.1")
    assert status.latest_patch == Version("3.15.2")
    assert status.newer_stable is None
    assert status.upcoming == Version("3.16.0b1")
    assert status.patch_behind


def test_python_status_up_to_date_with_stable_next() -> None:
    """Once the next version is out, it's reported as stable, not upcoming."""
    status = m.python_status([*RELEASES, release("Python 3.16.0")], "3.15.2")
    assert not status.patch_behind
    assert status.newer_stable == Version("3.16.0")
    assert status.upcoming is None


def test_python_status_on_an_older_branch() -> None:
    """On 3.14, the stable 3.15.2 is reported, and 3.16 as upcoming (live case)."""
    status = m.python_status(RELEASES, "3.14.2")
    assert status.latest_patch == Version("3.14.9")
    assert status.newer_stable == Version("3.15.2")
    assert status.upcoming == Version("3.16.0b1")


def test_python_status_on_a_prerelease_build() -> None:
    """A beta build counts as behind once that branch's final release is out."""
    status = m.python_status([release("Python 3.15.0")], "3.15.0b4")
    assert status.latest_patch == Version("3.15.0") and status.patch_behind
    assert status.newer_stable is None and status.upcoming is None


def test_check_python_reads_python_org() -> None:
    """The python.org downloads API is the source."""
    client = client_for({m.PYTHON_RELEASES_URL: RELEASES})
    assert m.check_python(client, "3.15.1").latest_patch == Version("3.15.2")


def test_check_python_offline_raises_a_clear_error() -> None:
    """Network failures become one error type the UI can show quietly."""
    with pytest.raises(m.MaintenanceError, match="python.org"):
        m.check_python(offline_client(), "3.15.1")


# ---------------------------------------------------------------------------
# Package updates (PyPI)
# ---------------------------------------------------------------------------


def test_find_updates_lists_newer_versions_only() -> None:
    """Only packages with a newer version on PyPI are reported, sorted by name."""
    client = client_for(
        {
            m.PYPI_JSON_URL.format(name="humanize"): pypi("4.12.0"),
            m.PYPI_JSON_URL.format(name="certifi"): pypi("2026.10.1"),
            m.PYPI_JSON_URL.format(name="anyio"): pypi("4.0.0"),
        }
    )
    updates = m.find_updates(
        client,
        {"humanize": "4.10.0", "certifi": "2026.1.1", "anyio": "4.0.0", "gone": "1.0"},
        critical={"certifi"},
    )
    assert [(u.name, str(u.installed), str(u.latest), u.critical) for u in updates] == [
        ("certifi", "2026.1.1", "2026.10.1", True),
        ("humanize", "4.10.0", "4.12.0", False),
    ]


def test_find_updates_offline_raises() -> None:
    """With no network the check fails clearly instead of reporting nothing."""
    with pytest.raises(m.MaintenanceError, match="PyPI"):
        m.find_updates(offline_client(), {"humanize": "4.10.0"})


def test_upgrade_requirements_pin_the_new_versions() -> None:
    """Updating asks the installer for exactly the versions that were found."""
    updates = [m.Update("humanize", Version("4.10.0"), Version("4.12.0"), False)]
    assert m.upgrade_requirements(updates) == ["humanize==4.12.0"]


# ---------------------------------------------------------------------------
# App health
# ---------------------------------------------------------------------------


def test_health_summary_states() -> None:
    """Up to date, or how many things need a new app build."""
    current = m.PythonStatus(Version("3.15.2"), Version("3.15.2"), None, None)
    behind = m.PythonStatus(Version("3.15.1"), Version("3.15.2"), None, None)
    certifi = m.Update("certifi", Version("1"), Version("2"), True)

    assert m.Health(current, []).summary == "✓ Up to date"
    summary = m.Health(behind, [certifi]).summary
    assert summary == "⚠ 2 updates need a new app build (TestFlight)"
    assert m.Health(current, [certifi]).summary.startswith("⚠ 1 update need")


def test_health_details_mention_versions() -> None:
    """The detail lines say what is behind and by how much."""
    status = m.PythonStatus(
        Version("3.15.1"), Version("3.15.2"), None, Version("3.16.0b1")
    )
    lines = m.Health(
        status, [m.Update("toga-core", Version("0.5.7"), Version("0.5.9"), True)]
    ).details()
    assert "Python 3.15.1 → 3.15.2 available" in lines
    assert "Python 3.16.0b1 is in pre-release" in lines
    assert "toga-core 0.5.7 → 0.5.9 (app-critical)" in lines


def test_newer_stable_python_counts_as_an_app_update() -> None:
    """A whole newer Python version also needs a new app build."""
    status = m.PythonStatus(
        Version("3.14.2"), Version("3.14.2"), Version("3.15.2"), None
    )
    health = m.Health(status, [])
    assert health.count == 1
    assert "Python 3.15.2 is out" in health.details()
