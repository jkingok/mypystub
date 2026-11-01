"""Permission status and a link to the app's Settings page, for the Setup view.

Internal to the launcher (#80): prototypes and examples must not import this.
Examples open Settings with their own few lines of standard code, so they still
run as standalone apps (see CLAUDE.md).
"""

import sys
from typing import Any

# The permissions the app declares (see pyproject.toml and #69), in display order
DECLARED = ("Location", "Camera", "Photo library", "Local network")

UNKNOWN = "Unknown"

# PHAuthorizationStatus, in value order
PHOTO_STATUS = ("Not asked yet", "Restricted", "Not allowed", "Allowed", "Limited")


def photo_status_text(value: int) -> str:
    """Describe a PHAuthorizationStatus value."""
    return PHOTO_STATUS[value] if 0 <= value < len(PHOTO_STATUS) else UNKNOWN


def toga_status(service: Any) -> str:
    """Describe a Toga hardware service's permission, if it can say."""
    try:
        granted = service.has_permission
    except Exception:  # noqa: BLE001  (not implemented on this platform)
        return UNKNOWN
    return "Allowed" if granted else "Not allowed (or not asked yet)"


def photo_status() -> str:
    """The photo library (add-only) permission, on iOS."""
    if sys.platform != "ios":
        return UNKNOWN
    from .bridge import PHAccessLevelAddOnly, PHPhotoLibrary

    return photo_status_text(
        int(PHPhotoLibrary.authorizationStatusForAccessLevel_(PHAccessLevelAddOnly))
    )


def status(app: Any) -> dict[str, str]:
    """Best-effort status of each declared permission.

    Location and camera come from Toga, the photo library from PHPhotoLibrary.
    iOS has no way to ask about local network access, so it's always Unknown.
    """
    return {
        "Location": toga_status(getattr(app, "location", None)),
        "Camera": toga_status(getattr(app, "camera", None)),
        "Photo library": photo_status(),
        "Local network": UNKNOWN,
    }


def open_app_settings() -> bool:
    """Open this app's page in the iOS Settings app. False off iOS.

    Must be called on the main thread.
    """
    if sys.platform != "ios":
        return False
    from toga_iOS.libs import NSURL

    from .bridge import app_settings_url, shared_application

    url = NSURL.URLWithString_(app_settings_url())
    shared_application().openURL_options_completionHandler_(url, {}, None)
    return True
