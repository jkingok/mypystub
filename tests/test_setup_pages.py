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


def test_health_section_states() -> None:
    """Not checked, a result with details, and offline."""
    assert setup_pages.NOT_CHECKED in setup_pages.health_section(None)

    status = maintenance.PythonStatus(Version("3.15.1"), Version("3.15.2"), None, None)
    page = setup_pages.health_section(maintenance.Health(status))
    assert "<li>Python 3.15.1 → 3.15.2 available</li>" in page

    assert "offline?" in setup_pages.health_section(None, "no network")


def test_the_packages_page_has_every_section() -> None:
    """Python, bundled (collapsed), user, updates, health and aliases, in order."""
    page = setup_pages.packages_html(
        "1 user package",
        {"humanize": "4.10.0"},
        None,
        python=[("Version", "3.15.2")],
        bundled={"toga-core": "0.5.7", "travertino": "0.5.7"},
        aliases=[("pyyaml", "pyyaml-pure (when no compatible wheel)")],
    )
    order = [
        "<h3>Python</h3>",
        "<h3>Bundled with the app</h3>",
        "<h3>User packages</h3>",
        "<h3>Updates</h3>",
        "<h3>App health</h3>",
        "<h3>Aliases</h3>",
    ]
    positions = [page.index(heading) for heading in order]
    assert positions == sorted(positions)
    assert "<details><summary>2 packages</summary>" in page
    assert "<td>toga-core</td><td>0.5.7</td>" in page
    assert "<td>pyyaml</td>" in page


def test_sections_left_out_when_there_is_nothing_for_them() -> None:
    """No bundled list or aliases given: those sections don't appear."""
    page = setup_pages.packages_html("none", {}, None)
    assert "Bundled with the app" not in page and "<h3>Aliases</h3>" not in page
    assert "<h3>Python</h3>" not in page


def test_permissions_page_lists_each_status() -> None:
    """One row per permission, and the Settings explanation."""
    page = setup_pages.permissions_html({"Location": "Allowed", "Camera": "Denied"})
    assert "<td>Location</td><td>Allowed</td>" in page
    assert "<td>Camera</td><td>Denied</td>" in page
    assert "Open Settings" in page


def test_local_network_note_only_when_it_is_listed() -> None:
    """The iOS-only local network note shows only with that row (not on Android)."""
    listed = setup_pages.permissions_html({"Local network": "Unknown"})
    assert "iOS has no way to ask about local network access" in listed
    android = setup_pages.permissions_html({"Location": "Allowed"})
    assert "local network" not in android


def test_text_is_escaped() -> None:
    """Package names, versions and errors can't inject HTML."""
    page = setup_pages.packages_html("<b>", {"<x>": "1"}, None, "<script>")
    assert "<script>" not in page and "&lt;x&gt;" in page
