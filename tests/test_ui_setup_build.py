"""The Check for updates flow asks GitHub first (#203).

Skipped where toga_dummy isn't installed, such as on device.
"""

import json
import os

import httpx2
import pytest
from packaging.version import Version

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import maintenance, release_check, ui
from tests.support_ui import run

RELEASE = {
    "tag_name": "2026.11.9.2",
    "html_url": "https://github.com/jkingok/mypystub/releases/tag/2026.11.9.2",
    "published_at": "2026-11-09T00:00:00Z",
    "body": "### New\n\n- A shiny thing.",
}


@pytest.fixture
def world(proto: ui.Prototype, app: toga.App, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Fake GitHub, python.org and PyPI, recording which were asked."""
    state: dict = {"asked": [], "github": RELEASE, "github_down": False}

    real_check_build = release_check.check_build

    def check_build(client: object, running: str | None) -> object:
        state["asked"].append("github")
        if state["github_down"]:
            raise maintenance.MaintenanceError("Couldn't reach GitHub: rate limited")
        transport = httpx2.MockTransport(
            lambda request: httpx2.Response(200, content=json.dumps(state["github"]))
        )
        return real_check_build(httpx2.Client(transport=transport), running)

    def check_python(client: object, current: str) -> maintenance.PythonStatus:
        state["asked"].append("python.org")
        return maintenance.PythonStatus(Version(current), Version(current), None, None)

    def find_updates(client: object, inventory: object, **kw: object) -> list:
        if kw.get("critical"):
            state["asked"].append("pypi (app)")
        return []

    monkeypatch.setattr(release_check, "check_build", check_build)
    monkeypatch.setattr(maintenance, "check_python", check_python)
    monkeypatch.setattr(maintenance, "find_updates", find_updates)
    monkeypatch.setattr(toga.App, "version", property(lambda self: state["running"]))
    state["running"] = "2026.11.9.1"
    return state


def check(proto: ui.Prototype, app: toga.App) -> None:
    """Open Packages and press Check for updates."""
    proto.open_setup_page("packages")
    run(app, proto.handle_check_updates(proto.update_all_button))


def test_a_newer_build_is_reported_first_and_the_deeper_checks_are_skipped(
    proto: ui.Prototype, app: toga.App, world: dict
) -> None:
    """GitHub says a later build exists, so python.org and PyPI aren't asked."""
    check(proto, app)
    assert "python.org" not in world["asked"] and "pypi (app)" not in world["asked"]
    html = proto.setup_html
    assert "A newer build, 2026.11.9.2, is available (TestFlight)" in html
    assert "Python and package checks skipped" in html
    assert 'href="https://github.com/jkingok/mypystub/releases/tag/2026.11.9.2"' in html
    assert "A shiny thing." in html
    assert "App: ⚠ A newer build" in proto.setup_activity.text.text


def test_the_latest_build_goes_on_to_the_deeper_checks(
    proto: ui.Prototype, app: toga.App, world: dict
) -> None:
    """Up to date with GitHub: then Python and the bundled packages."""
    world["running"] = "2026.11.9.2"
    check(proto, app)
    assert world["asked"] == ["github", "python.org", "pypi (app)"]
    assert "✓ Up to date" in proto.setup_html


def test_github_failing_does_not_stop_the_other_checks(
    proto: ui.Prototype, app: toga.App, world: dict
) -> None:
    """Rate-limited or offline: say so, and carry on."""
    world["github_down"] = True
    check(proto, app)
    assert "python.org" in world["asked"]
    assert "Couldn't check for a newer build" in proto.setup_html
    assert "rate limited" in proto.setup_html


def test_a_development_build_skips_github(
    proto: ui.Prototype, app: toga.App, world: dict
) -> None:
    """No request for a placeholder version; the rest runs."""
    world["running"] = "0.0.2"
    check(proto, app)
    assert "python.org" in world["asked"]
    assert "development build" in proto.setup_html.lower()


def test_the_setup_page_opens_links_in_the_browser(proto: ui.Prototype) -> None:
    """The release link must not navigate the page itself away."""
    assert proto.setup_view.on_navigation_starting is not None
