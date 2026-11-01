"""Take a photo with the camera and save it to your photo library."""

import asyncio
import sys
from ctypes import c_void_p

import toga


def save_to_photo_library(photo: toga.Image) -> None:
    """Save `photo` to Photos. iOS asks for permission the first time."""
    from rubicon.objc.runtime import (  # pyright: ignore[reportMissingImports]
        load_library,
    )

    uikit = load_library("UIKit")
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
        return "Camera permission was not granted."
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
    print(future.result(timeout=300))
else:
    print("No app running?")
