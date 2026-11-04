import ctypes

import toga
from rubicon.objc import ObjCClass, ObjCInstance  # pyright: ignore[reportMissingImports]

# 1. Load the native UIKit library via ctypes
uikit = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/UIKit.framework/UIKit")

# 2. Define the exact input/output footprint for the image conversion function
UIImagePNGRepresentation = uikit.UIImagePNGRepresentation
UIImagePNGRepresentation.argtypes = [ctypes.c_void_p]  # Expects a pointer to a UIImage
UIImagePNGRepresentation.restype = ctypes.c_void_p  # Returns a pointer to NSData


def write_uiimage_to_file(
    ui_image_instance: ObjCInstance, destination_path: str
) -> bool:
    """
    Takes a Rubicon ObjCInstance of a UIImage, extracts its raw PNG bytes,
    and writes it directly to a local file path.
    """
    if ui_image_instance is None:
        print("Error: Received a NoneType instead of a UIImage.")
        return False

    # Extract the raw memory pointer (.ptr) from the Rubicon object
    # and pass it to the native C function
    raw_nsdata_ptr = UIImagePNGRepresentation(ui_image_instance.ptr)

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
    # Defensive check: ensure this only fires when running on iOS
    if toga.platform.current_platform != "iOS":  # pyright: ignore[reportAttributeAccessIssue]
        print("This feature is only available on iOS.")
        return False

    # 1. Load the required UIKit and Foundation classes
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
