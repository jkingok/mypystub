"""Plain helpers for the launcher's screens: iPad detection, backups, sharing."""

from __future__ import annotations

import io
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import toga

from .bridge import (
    UIModalPresentationFormSheet,
    UIPopoverArrowDirectionDown,
    UIUserInterfaceIdiomPad,
)

# The app's own Python source, as shipped inside the bundle: this package's
# folder. Sharing it is a backstop to the About page's Source link, so anyone
# can read exactly what is running without trusting that link.
APP_SOURCE_DIR = Path(__file__).resolve().parent


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


def create_source_zip(app: toga.App) -> Path:
    """Zip the app's own Python source (this package) for sharing or review.

    Everything in the package folder as shipped is included, in sorted order so
    the listing is stable, apart from ``__pycache__``. The file is named with
    the app's version, and written to the cache directory for a transient share.
    """
    name = f"{app.formal_name.lower().replace(' ', '_')}-{app.version}-source.zip"
    app.paths.cache.mkdir(parents=True, exist_ok=True)
    dest = app.paths.cache / name
    with ZipFile(dest, "w", ZIP_DEFLATED) as archive:
        for item in sorted(APP_SOURCE_DIR.rglob("*")):
            relative = item.relative_to(APP_SOURCE_DIR)
            if item.is_file() and "__pycache__" not in relative.parts:
                archive.write(item, Path(APP_SOURCE_DIR.name) / relative)
    return dest


def share_anchor_rect(width: float, height: float) -> tuple[float, float, float, float]:
    """
    Where a share popover points: a zero-size spot at the bottom centre of a view.

    Never the whole view, which leaves a popover no room but a sliver at the side.

    :param width: The presenting view's width, in points.
    :param height: The presenting view's height, in points.
    :returns: ``(x, y, width, height)`` of the anchor, inside the view.
    """
    return (width / 2, max(height - 1, 0.0), 0.0, 0.0)


def configure_share_presentation(
    activity_vc: Any,
    presenting_view: Any,
    make_rect: Callable[[float, float, float, float], Any],
) -> None:
    """
    Presents a share sheet as a form sheet, anchored safely if iOS makes it a popover.

    rubicon reads ``popoverPresentationController`` as a method, because UIKit
    declares it in a category, so it has to be called. Setting attributes on it
    uncalled only touches a Python object, and an iPad then ends the app for
    want of a source view.

    :param activity_vc: The ``UIActivityViewController`` about to be presented.
    :param presenting_view: The view of the controller that presents it.
    :param make_rect: Builds a native rectangle from ``(x, y, width, height)``.
    """
    activity_vc.modalPresentationStyle = UIModalPresentationFormSheet
    popover = activity_vc.popoverPresentationController()
    if popover is not None:
        size = presenting_view.bounds.size
        popover.sourceView = presenting_view
        popover.sourceRect = make_rect(*share_anchor_rect(size.width, size.height))
        popover.permittedArrowDirections = UIPopoverArrowDirectionDown


def open_share_sheet(w: toga.Widget, file_path: Path) -> None:
    """
    Opens the iOS native share sheet for a specific HTML file.

    :param w: The active Toga widget instance initiating the share.
    :param file_path: Absolute string path to the local file.
    """
    if sys.platform == "ios":
        from rubicon.objc import NSMakeRect
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

            # 5. A full-width sheet, with a safe anchor in case iOS uses a popover
            configure_share_presentation(activity_vc, presenting_vc.view, NSMakeRect)

            # 6. Present the share sheet asynchronously over the top of the interface
            presenting_vc.presentViewController(
                activity_vc, animated=True, completion=None
            )
