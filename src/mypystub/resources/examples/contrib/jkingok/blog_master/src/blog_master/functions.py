"""Clipboard helpers: images and text from the iOS pasteboard or Android's clipboard.

The iOS parts (Rubicon and UIKit) are only loaded by the iOS functions, when
they're called on iOS, so the app starts anywhere.
"""

import ctypes
import sys
from typing import Any


def png_representation() -> Any:
    """UIKit's UIImagePNGRepresentation, through ctypes (iOS only)."""
    uikit = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/UIKit.framework/UIKit")
    function = uikit.UIImagePNGRepresentation
    function.argtypes = [ctypes.c_void_p]  # Expects a pointer to a UIImage
    function.restype = ctypes.c_void_p  # Returns a pointer to NSData
    return function


def clipboard_text() -> str | None:
    """The text on Android's clipboard: None if there's none, or not on Android."""
    if sys.platform != "android":
        return None
    from java import jclass  # pyright: ignore[reportMissingImports]

    activity = jclass("org.beeware.android.MainActivity").singletonThis
    Context = jclass("android.content.Context")
    clipboard = activity.getSystemService(Context.CLIPBOARD_SERVICE)
    clip = clipboard.getPrimaryClip()
    if clip is None or clip.getItemCount() == 0:
        return None
    text = clip.getItemAt(0).coerceToText(activity)
    return str(text) if text is not None else None


def android_image_to_file(destination_path: str) -> bool:
    """Save the image on Android's clipboard to `destination_path`.

    Apps copy an image as a ``content://`` URI on the clip item, with an
    ``image/*`` type in the clip's description. Its bytes are saved as they
    are (PNG, JPEG, ...); Toga's image loading reads the format from the data.
    """
    from java import jarray, jbyte, jclass  # pyright: ignore[reportMissingImports]

    activity = jclass("org.beeware.android.MainActivity").singletonThis
    Context = jclass("android.content.Context")
    clipboard = activity.getSystemService(Context.CLIPBOARD_SERVICE)
    clip = clipboard.getPrimaryClip()
    if clip is None or clip.getItemCount() == 0:
        print("The clipboard is empty.")
        return False
    description = clip.getDescription()
    resolver = activity.getContentResolver()
    for index in range(clip.getItemCount()):
        uri = clip.getItemAt(index).getUri()
        if uri is None:
            continue
        kind = str(resolver.getType(uri) or "")
        if not kind and description is not None and description.hasMimeType("image/*"):
            kind = "image/*"
        if not kind.startswith("image/"):
            continue
        stream = resolver.openInputStream(uri)
        if stream is None:
            continue
        buffer, data = jarray(jbyte)(65536), bytearray()
        try:
            while (count := stream.read(buffer)) >= 0:
                data += bytes(memoryview(buffer))[:count]
        finally:
            stream.close()
        if not data:
            continue
        try:
            with open(destination_path, "wb") as f:
                f.write(data)
        except OSError as e:
            print(f"Failed to write file to disk: {e}")
            return False
        return True
    print("No image found on the clipboard.")
    return False


def write_uiimage_to_file(ui_image_instance: Any, destination_path: str) -> bool:
    """
    Takes a Rubicon ObjCInstance of a UIImage, extracts its raw PNG bytes,
    and writes it directly to a local file path.
    """
    from rubicon.objc import ObjCInstance  # pyright: ignore[reportMissingImports]

    if ui_image_instance is None:
        print("Error: Received a NoneType instead of a UIImage.")
        return False

    # Extract the raw memory pointer (.ptr) from the Rubicon object
    # and pass it to the native C function
    raw_nsdata_ptr = png_representation()(ui_image_instance.ptr)

    if not raw_nsdata_ptr:
        print("Error: Could not extract PNG bytes from the UIImage.")
        return False

    # Wrap the returned pointer back into a usable Rubicon NSData object
    png_data = ObjCInstance(raw_nsdata_ptr)

    # Access the raw buffer pointer and the total data size (in bytes)
    data_bytes_pointer = png_data.bytes
    data_length = png_data.length

    # Safely mirror that raw memory block into Python's memory space
    python_buffer = ctypes.string_at(data_bytes_pointer, data_length)

    # Save the raw data block to disk
    try:
        with open(destination_path, "wb") as f:
            f.write(python_buffer)
        return True
    except Exception as e:  # noqa: BLE001 (report any failure to the user)
        print(f"Failed to write file to disk: {e}")
        return False


def save_image_from_pasteboard(destination_filename: str) -> bool:
    """
    Checks the iOS pasteboard for an image, converts it to PNG data,
    and saves it to the app's documents directory.
    Returns True if successful, False otherwise.
    """
    # Images come from the iOS pasteboard or Android's clipboard; elsewhere, say so
    if sys.platform == "android":
        return android_image_to_file(destination_filename)
    if sys.platform != "ios":
        print("Pasting an image is only available on iOS and Android.")
        return False

    # 1. Load the required UIKit and Foundation classes
    from rubicon.objc import ObjCClass  # pyright: ignore[reportMissingImports]

    UIPasteboard = ObjCClass("UIPasteboard")

    # 2. Get the general system clipboard
    pasteboard = UIPasteboard.generalPasteboard

    # Check if an image actually exists on the pasteboard
    if not pasteboard.hasImages:
        print("No image found on the pasteboard.")
        return False

    # 3. Retrieve the UIImage object
    native_image = pasteboard.image
    if native_image is None:
        print("Failed to pull the image from the pasteboard.")
        return False

    return write_uiimage_to_file(native_image, destination_filename)
