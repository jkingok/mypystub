"""Plain helpers for the launcher's screens: iPad detection, backups, sharing."""

from __future__ import annotations

import io
import sys
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import toga

UIUserInterfaceIdiomPad = 1


def is_ipad_from_window(toga_window: toga.Window) -> bool:
    """Detects iPad idiom via the native UIWindow / UIViewController trait collection."""
    # Toga's underlying UIKit native object (UIWindow or UIViewController)
    return (
        sys.platform == "ios"
        and toga_window._impl.native.traitCollection.userInterfaceIdiom
        == UIUserInterfaceIdiomPad
    )  # pyright: ignore[reportPrivateUsage]


def zip_directory_to_bytes(source_dir: Path) -> bytes:
    """Recursively archives a directory into a zip file stored in memory as bytes."""
    zip_buffer = io.BytesIO()

    if source_dir.exists():
        with ZipFile(zip_buffer, "w", ZIP_DEFLATED) as zip_file:
            # rglob("*") grabs everything recursively
            for item in source_dir.rglob("*"):
                if item.is_file():
                    # relative_to ensures we don't include absolute iOS system paths
                    archive_name = item.relative_to(source_dir)
                    zip_file.write(item, archive_name)

    return zip_buffer.getvalue()


def create_nested_app_backup(app: toga.App) -> Path:
    """
    Creates a master backup zip containing data.zip and config.zip in memory,
    then writes the master file out to the app's cache directory.

    Args:
        app: The running toga.App instance (e.g., self inside an app class)

    Returns:
        Path: The location of the final master zip file on disk.
    """
    # 1. Resolve Toga's native paths
    cache_dir = app.paths.cache
    config_dir = app.paths.config
    data_dir = getattr(app, "user_documents_dir", app.paths.data)

    # 2. Build sub-archives in memory as bytes
    print(f"Archiving cache directory: {cache_dir}")
    cache_zip_bytes = zip_directory_to_bytes(cache_dir)

    print(f"Archiving config directory: {config_dir}")
    config_zip_bytes = zip_directory_to_bytes(config_dir)

    print(f"Archiving data directory: {data_dir}")
    data_zip_bytes = zip_directory_to_bytes(data_dir)

    # 3. Create the master zip filename using the app's identifier and timestamp
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    master_filename = f"{app.formal_name.lower().replace(' ', '_')}-{timestamp}.zip"

    # We write the final file to the app's cache directory (safe for transient shares)
    master_zip_path = app.paths.cache / master_filename
    app.paths.cache.mkdir(parents=True, exist_ok=True)

    # 4. Pack the memory archives into the final master zip on disk
    with ZipFile(master_zip_path, "w", ZIP_DEFLATED) as master_zip:
        # writestr allows passing raw bytes and assigning an internal archive filename
        master_zip.writestr("cache.zip", cache_zip_bytes)
        master_zip.writestr("config.zip", config_zip_bytes)
        master_zip.writestr("data.zip", data_zip_bytes)

    print(f"Structured master archive created at: {master_zip_path}")
    return master_zip_path


def open_share_sheet(w: toga.Widget, file_path: Path) -> None:
    """
    Opens the iOS native share sheet for a specific HTML file.

    :param w: The active Toga widget instance initiating the share.
    :param file_path: Absolute string path to the local file.
    """
    if sys.platform == "ios":
        from toga_iOS.libs import NSURL, NSMutableArray

        from .bridge import UIActivityViewController

        # 1. Ensure the file path exists and convert it into a native file URL
        absolute_path = str(file_path.resolve())
        file_url = NSURL.fileURLWithPath_(absolute_path)

        # 2. Add the URL asset into an Objective-C array of items to share
        share_items = NSMutableArray.alloc().init()
        share_items.addObject_(file_url)

        # 3. Initialize the native UIActivityViewController
        # Pass None for custom applicationActivities to use standard system defaults
        activity_vc = UIActivityViewController.alloc().initWithActivityItems(
            share_items, applicationActivities=None
        )

        # 4. Grab the native UIViewController backing your Toga Window
        if w.app and w.app.main_window:
            assert isinstance(w.app.main_window, toga.MainWindow)
            presenting_vc = w.app.main_window._impl.native.rootViewController

            # 5. Handle iPad popover configurations safely to prevent crashes
            if activity_vc.popoverPresentationController:
                # Anchor the popover menu to the center or bounds of the current view frame
                activity_vc.popoverPresentationController.sourceView = (
                    presenting_vc.view
                )
                activity_vc.popoverPresentationController.sourceRect = (
                    presenting_vc.view.bounds
                )
                # Optional: restrict arrow directions if needed
                # activity_vc.popoverPresentationController.permittedArrowDirections = 0

            # 6. Present the share sheet asynchronously over the top of the interface
            presenting_vc.presentViewController(
                activity_vc, animated=True, completion=None
            )
