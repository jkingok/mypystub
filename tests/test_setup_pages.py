"""The Setup detail pages' HTML (no Toga needed)."""

from packaging.version import Version

from mypystub import maintenance, setup_pages


def update(name: str, old: str, new: str) -> maintenance.Update:
    """An Update for `name` from `old` to `new`."""
    return maintenance.Update(name, Version(old), Version(new), False)


def test_packages_page_states() -> None:
    """Not checked, up to date, updates found, and a failed check."""
    inventory = {"humanize": "4.10.0"}
    unchecked = setup_pages.packages_html("1 user package (1 KB)", inventory, None)
    assert "<td>humanize</td><td>4.10.0</td>" in unchecked
    assert setup_pages.NOT_CHECKED in unchecked

    assert "✓ Up to date" in setup_pages.packages_html("x", inventory, [])

    found = setup_pages.packages_html(
        "x", inventory, [update("humanize", "4.10.0", "4.12.0")]
    )
    assert "<td>humanize</td><td>4.10.0 → 4.12.0</td>" in found

    failed = setup_pages.packages_html("x", inventory, None, "offline")
    assert "check: offline" in failed


def test_health_page_states() -> None:
    """Not checked, a result with details, and offline."""
    assert setup_pages.NOT_CHECKED in setup_pages.health_html(None)

    status = maintenance.PythonStatus(Version("3.15.1"), Version("3.15.2"), None, None)
    page = setup_pages.health_html(maintenance.Health(status))
    assert "<li>Python 3.15.1 → 3.15.2 available</li>" in page

    assert "offline?" in setup_pages.health_html(None, "no network")


def test_permissions_page_lists_each_status() -> None:
    """One row per permission, and the Settings explanation."""
    page = setup_pages.permissions_html({"Location": "Allowed", "Camera": "Denied"})
    assert "<td>Location</td><td>Allowed</td>" in page
    assert "<td>Camera</td><td>Denied</td>" in page
    assert "Open Settings" in page


def test_text_is_escaped() -> None:
    """Package names, versions and errors can't inject HTML."""
    page = setup_pages.packages_html("<b>", {"<x>": "1"}, None, "<script>")
    assert "<script>" not in page and "&lt;x&gt;" in page
