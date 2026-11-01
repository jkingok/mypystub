"""Ask for location permission and print where you are."""

import asyncio
import sys

import toga
from toga.hardware.location import Location

# CLAuthorizationStatus.notDetermined: the user hasn't answered the prompt yet
NOT_DETERMINED = 0

DENIED = "Location permission was not granted."


def open_settings(app: toga.App) -> None:
    """Open this app's page in iOS Settings, where its permissions are."""
    if sys.platform != "ios":
        print("Change it in your system's privacy settings.")
        return
    import webbrowser

    from rubicon.objc import objc_const  # pyright: ignore[reportMissingImports]
    from toga_iOS.libs import uikit  # pyright: ignore[reportMissingImports]

    url = str(objc_const(uikit, "UIApplicationOpenSettingsURLString"))
    # UIKit must be used on the main thread, which runs the app's loop
    app.loop.call_soon_threadsafe(webbrowser.open, url)


def offer_settings(app: toga.App, what: str) -> None:
    """Ask whether to open Settings to allow `what`."""
    answer = input(f"Open Settings to allow {what}? [y/N] ")
    if answer.strip().lower().startswith("y"):
        open_settings(app)


def undecided(location: Location) -> bool:
    """Whether iOS is still waiting for the user to answer the location prompt."""
    native = getattr(location._impl, "native", None)
    return getattr(native, "authorizationStatus", None) == NOT_DETERMINED


async def where_am_i(app: toga.App, timeout: float = 60.0) -> str:
    """Request permission, then return the current position as text."""
    location = app.location
    granted = await location.request_permission()
    # Toga's iOS backend can answer before the user does: iOS reports the
    # still-undecided status as soon as the location manager is created, and
    # that first report resolves the request. Wait for the user's real answer.
    waited = 0.0
    while not granted and undecided(location) and waited < timeout:
        await asyncio.sleep(0.25)
        waited += 0.25
        granted = location.has_permission
    if not granted:
        return DENIED
    here = await location.current_location()
    return f"You are at {here.lat:.5f}, {here.lng:.5f}"


if app := toga.App.app:
    # This script runs on a background thread; Toga's APIs run on the app loop.
    future = asyncio.run_coroutine_threadsafe(where_am_i(app), app.loop)
    message = future.result(timeout=90)
    print(message)
    if message == DENIED:
        offer_settings(app, "location")
else:
    print("No app running?")
