"""The launcher's permission status and Settings link (#80)."""

from types import SimpleNamespace

import pytest

from mypystub import permissions


def fake_app(location: bool | None, camera: bool | None) -> SimpleNamespace:
    """An app whose Toga permission checks answer as given (None: raises)."""

    def check(granted: bool | None) -> SimpleNamespace:
        if granted is None:
            return SimpleNamespace()  # no has_permission: platform can't say
        return SimpleNamespace(has_permission=granted)

    return SimpleNamespace(location=check(location), camera=check(camera))


def test_open_app_settings_is_ios_only() -> None:
    """Off iOS there's no Settings app to open."""
    assert permissions.open_app_settings() is False


def test_status_lists_every_declared_permission() -> None:
    """Location and camera come from Toga; the rest is unknown off iOS."""
    status = permissions.status(fake_app(location=True, camera=False))
    assert status == {
        "Location": "Allowed",
        "Camera": "Not allowed (or not asked yet)",
        "Photo library": "Unknown",
        "Local network": "Unknown",
    }


def test_android_shows_only_location_and_camera(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Android lists just what the examples use; the other rows are iOS-only."""
    monkeypatch.setattr(permissions.sys, "platform", "android")
    status = permissions.status(fake_app(location=True, camera=False))
    assert status == {
        "Location": "Allowed",
        "Camera": "Not allowed (or not asked yet)",
    }


def test_status_tolerates_platforms_without_checks() -> None:
    """A platform without a permission API reports Unknown, not an error."""
    status = permissions.status(fake_app(location=None, camera=None))
    assert set(status.values()) == {"Unknown"}


def test_photo_status_names() -> None:
    """PHAuthorizationStatus values read naturally."""
    assert [permissions.photo_status_text(n) for n in range(5)] == [
        "Not asked yet",
        "Restricted",
        "Not allowed",
        "Allowed",
        "Limited",
    ]
