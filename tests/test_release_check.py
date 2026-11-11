"""Asking GitHub whether this is the latest build (#203). No Toga needed."""

import json

import httpx2
import pytest

from mypystub import maintenance, release_check


def client(handler) -> httpx2.Client:
    """A client whose requests go to `handler`."""
    return httpx2.Client(transport=httpx2.MockTransport(handler))


def answering(payload, status: int = 200):
    """A handler that records requests and answers with `payload`."""
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(status, content=json.dumps(payload))

    handler.seen = seen  # type: ignore[attr-defined]
    return handler


RELEASE = {
    "tag_name": "2026.11.9.2",
    "html_url": "https://github.com/jkingok/mypystub/releases/tag/2026.11.9.2",
    "published_at": "2026-11-09T04:05:06Z",
    "body": "### New\n\n- A thing.",
}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026.11.9.1", (2026, 11, 9, 1)),
        ("2026.11.10.1", (2026, 11, 10, 1)),
        ("2026.1.2.30", (2026, 1, 2, 30)),
        ("0.0.2", None),
        ("2026.11.9", None),
        ("2026.11.09.1", None),
        ("2026.11.9.0", None),
        ("v2026.11.9.1", None),
        ("2026.11.9.1.dev0", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_version(text: str | None, expected: tuple | None) -> None:
    """Only YYYY.M.D.N, without zero padding, is a release build."""
    assert release_check.parse_version(text) == expected


def test_versions_compare_as_numbers_not_text() -> None:
    """2026.11.10.1 is after 2026.11.9.1, though it sorts before as text."""
    ten = release_check.parse_version("2026.11.10.1")
    nine = release_check.parse_version("2026.11.9.1")
    assert ten is not None and nine is not None and nine < ten
    texts = ["2026.11.9.1", "2026.11.10.1"]
    assert sorted(texts) == ["2026.11.10.1", "2026.11.9.1"]  # as text it is wrong


@pytest.mark.parametrize(
    ("running", "kind"),
    [
        ("2026.11.9.1", "newer"),
        ("2026.11.9.2", "current"),
        ("2026.11.9.3", "ahead"),
        ("2026.11.10.1", "ahead"),
        ("2026.10.30.9", "newer"),
    ],
)
def test_comparison_against_the_latest_release(running: str, kind: str) -> None:
    """A build is current, behind, or ahead of the newest Release."""
    handler = answering(RELEASE)
    status = release_check.check_build(client(handler), running)
    assert status.kind == kind and status.latest == "2026.11.9.2"
    assert len(handler.seen) == 1
    assert str(handler.seen[0].url).endswith("/repos/jkingok/mypystub/releases/latest")
    assert "authorization" not in handler.seen[0].headers  # anonymous


def test_a_newer_build_carries_its_page_date_and_notes() -> None:
    """What the health page shows for it."""
    status = release_check.check_build(client(answering(RELEASE)), "2026.11.9.1")
    assert status.newer and status.published == "2026-11-09"
    assert status.url.endswith("/releases/tag/2026.11.9.2")
    assert "A thing." in status.notes
    assert "2026.11.9.2 (2026-11-09) is available in TestFlight" in status.lines()[0]


def test_long_notes_are_cut_short() -> None:
    """The notes excerpt stays small."""
    long = dict(RELEASE, body="x" * 5000)
    status = release_check.check_build(client(answering(long)), "2026.11.9.1")
    assert status.notes == "x" * release_check.NOTES_LIMIT + "\n\n…"


def test_long_notes_are_cut_at_a_line_end() -> None:
    """So a Markdown list item or heading is never cut in half."""
    lines = [f"- Item number {n} of the release notes." for n in range(40)]
    status = release_check.check_build(
        client(answering(dict(RELEASE, body="\n".join(lines)))), "2026.11.9.1"
    )
    kept = status.notes.split("\n\n…")[0].split("\n")
    assert status.notes.endswith("\n\n…") and kept == lines[: len(kept)]
    assert len(status.notes) <= release_check.NOTES_LIMIT + 3


def test_a_development_build_costs_no_request() -> None:
    """Placeholder versions aren't compared with anything."""
    handler = answering(RELEASE)
    for running in ("0.0.2", "", None):
        status = release_check.check_build(client(handler), running)
        assert status.kind == "not_release" and not status.newer
    assert handler.seen == []
    assert "development build" in status.lines()[0].lower()


def test_being_ahead_is_explained_and_current_says_nothing() -> None:
    """A build just uploaded is not an error."""
    ahead = release_check.check_build(client(answering(RELEASE)), "2026.11.9.3")
    assert "probably not released yet" in ahead.lines()[0]
    current = release_check.check_build(client(answering(RELEASE)), "2026.11.9.2")
    assert current.lines() == []


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        ({"message": "Not Found"}, 404),  # no Release yet
        ({"message": "API rate limit exceeded"}, 403),
        ({"message": "Too Many Requests"}, 429),
        ([], 200),
        ({"tag_name": 5}, 200),
        ({"name": "no tag"}, 200),
    ],
)
def test_failures_become_maintenance_errors(payload: object, status: int) -> None:
    """The caller reports 'couldn't check' and carries on."""
    with pytest.raises(maintenance.MaintenanceError):
        release_check.check_build(client(answering(payload, status)), "2026.11.9.1")


def test_a_latest_tag_that_is_not_a_build_version_is_an_error() -> None:
    """A hand-made Release called v1 can't be compared."""
    with pytest.raises(maintenance.MaintenanceError, match="isn't a build version"):
        release_check.check_build(
            client(answering(dict(RELEASE, tag_name="v1.0"))), "2026.11.9.1"
        )


def test_a_dropped_connection_is_a_maintenance_error() -> None:
    """Offline."""

    def offline(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("no network", request=request)

    with pytest.raises(maintenance.MaintenanceError, match="GitHub"):
        release_check.check_build(client(offline), "2026.11.9.1")


def test_health_counts_a_newer_build_and_skips_the_rest() -> None:
    """A newer build is the one finding, and the others are said to be skipped."""
    status = release_check.check_build(client(answering(RELEASE)), "2026.11.9.1")
    health = maintenance.Health(None, [], status)
    assert health.count == 1
    assert health.summary == "⚠ A newer build, 2026.11.9.2, is available (TestFlight)"
    lines = health.details()
    assert lines[0].startswith("Build 2026.11.9.2")
    assert lines[-1] == "Python and package checks skipped: update the app first."


def test_health_without_a_build_check_is_as_before() -> None:
    """Existing results and wording are unchanged."""
    python = maintenance.PythonStatus(
        maintenance.Version("3.15.1"), maintenance.Version("3.15.2"), None, None
    )
    health = maintenance.Health(python)
    assert health.count == 1 and "Python 3.15.1 → 3.15.2 available" in health.details()
