"""Take a photo with the camera and save it to your photo library."""

import asyncio
import sys
from ctypes import c_void_p

import toga

DENIED = "Camera permission was not granted."


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


def save_to_photo_library(photo: toga.Image) -> None:
    """Save `photo` to Photos. iOS asks for permission the first time."""
    # Toga has already loaded UIKit; reuse its library handle
    from toga_iOS.libs import uikit  # pyright: ignore[reportMissingImports]

    save = uikit.UIImageWriteToSavedPhotosAlbum
    save.argtypes = [c_void_p, c_void_p, c_void_p, c_void_p]
    save.restype = None
    # The UIImage behind the toga.Image; no completion callback
    save(photo._impl.native.ptr, None, None, None)


async def take_and_save(app: toga.App) -> str:
    """Ask for camera permission, take a photo, and save it."""
    camera = app.camera
    if not camera.devices:
        return "No camera available (the iOS Simulator has none)."
    if not await camera.request_permission():
        return DENIED
    photo = await camera.take_photo()
    if photo is None:
        return "No photo taken."
    if sys.platform != "ios":
        return f"Took a {photo.width}x{photo.height} photo."
    save_to_photo_library(photo)
    return f"Saved a {photo.width}x{photo.height} photo to your photo library."


if app := toga.App.app:
    # This script runs on a background thread; Toga's APIs run on the app loop.
    future = asyncio.run_coroutine_threadsafe(take_and_save(app), app.loop)
    message = future.result(timeout=300)
    print(message)
    if message == DENIED:
        offer_settings(app, "the camera")
else:
    print("No app running?")
