"""Objective-C classes the launcher needs that toga_iOS doesn't provide.

Import Objective-C classes from ``toga_iOS.libs`` whenever it has them: a second
``ObjCClass`` for the same class can clash with toga_iOS's copy ("multiple
implementation" errors), and toga_iOS also declares class properties on its
copies. Only classes, and frameworks, that toga_iOS doesn't set up belong here,
in this one place (enforced by tests/test_objc_usage.py).

Everything is defined on iOS only, so desktop and CI can import this module.
Re-check this list against toga_iOS.libs when Toga is upgraded: anything it
gains should be imported from there instead.
"""

import asyncio
import sys
from pathlib import Path
from typing import Any

from . import paste_import

if sys.platform == "ios":
    from rubicon.objc import (  # pyright: ignore[reportMissingImports]
        ObjCClass,
        objc_const,
    )
    from rubicon.objc.runtime import (  # pyright: ignore[reportMissingImports]
        load_library,
    )
    from toga_iOS.libs import UIApplication, uikit

    # UIKit: not declared in toga_iOS.libs.uikit
    UIActivityViewController = ObjCClass("UIActivityViewController")

    def app_settings_url() -> str:
        """UIApplicationOpenSettingsURLString: opens this app's Settings page."""
        return str(objc_const(uikit, "UIApplicationOpenSettingsURLString"))

    def shared_application() -> Any:
        """UIApplication.sharedApplication, whether or not it's declared a property."""
        shared = UIApplication.sharedApplication
        return shared() if callable(shared) else shared

    # UIKit's pasteboard (the clipboard); toga_iOS doesn't declare it
    UIPasteboard = ObjCClass("UIPasteboard")

    # Photos: Toga doesn't load this framework, so it's loaded here
    photos = load_library("Photos")
    PHPhotoLibrary = ObjCClass("PHPhotoLibrary")
    PHAccessLevelAddOnly = 1  # PHAccessLevel.addOnly


# Seconds to wait for a copied file, which might have to download from iCloud
PASTE_TIMEOUT = 120.0

# Blocks whose callback may still come after the wait gave up: rubicon frees a
# Block's callback along with the Block, so these have to outlive the wait
_abandoned_blocks: list[Any] = []


async def _load_file(provider: Any, uti: str, into: Path) -> Path:
    """Copy what `provider` holds as `uti` into the folder `into`.

    The system's file only lasts until the callback returns, and the callback
    comes on a background thread, so it's copied there and the result is handed
    back to the event loop.
    """
    from rubicon.objc import (  # pyright: ignore[reportMissingImports]
        Block,
        ObjCInstance,
        objc_id,
    )

    loop = asyncio.get_running_loop()
    loaded: asyncio.Future[Path] = loop.create_future()

    def deliver(path: Path | None, problem: OSError | None) -> None:
        if loaded.done():  # the wait gave up
            return
        if path is None:
            loaded.set_exception(problem or OSError("The file couldn't be read."))
        else:
            loaded.set_result(path)

    def finished(url: Any, error: Any) -> None:
        path, problem = None, None
        try:
            if url:
                source = Path(str(ObjCInstance(url).path))
                path = paste_import.keep_copy(source, into)
            elif error:
                message = str(ObjCInstance(error).localizedDescription)
                problem = OSError(f"{message}. If iOS asks, choose Allow Paste.")
        except OSError as failure:
            problem = failure
        loop.call_soon_threadsafe(deliver, path, problem)

    block = Block(finished, None, objc_id, objc_id)
    provider.loadFileRepresentationForTypeIdentifier(uti, completionHandler=block)
    try:
        return await asyncio.wait_for(loaded, PASTE_TIMEOUT)
    except TimeoutError:
        _abandoned_blocks.append(block)
        raise OSError("The copied file took too long to arrive.") from None


async def read_pasteboard(into: Path) -> tuple[str, str] | None:
    """What the system pasteboard (clipboard) holds, or None if nothing useful.

    Returns ``("file", path)`` for a copied file, which is preferred, or
    ``("text", string)`` for copied text. Pasteboards only exist on iOS: on
    other platforms this returns None.

    The Files app offers a copied file through an item provider, not a URL, so
    the file is copied into the folder `into`, replacing what was there from the
    last paste. A file URL lives outside the app, so its security-scoped access
    is started here and left open for the copy that follows; the system reclaims
    it when the app quits. Raises ValueError for a copied folder, and OSError if
    the file can't be read.
    """
    if sys.platform != "ios":
        return None
    pasteboard = UIPasteboard.generalPasteboard
    if pasteboard.hasURLs:
        url = pasteboard.URL
        if url is not None and url.isFileURL:
            url.startAccessingSecurityScopedResource()
            return ("file", str(url.path))
    has_text = bool(pasteboard.hasStrings)
    providers = list(pasteboard.itemProviders)
    if providers:  # only the first of several copied files
        types = [str(uti) for uti in providers[0].registeredTypeIdentifiers]
        if paste_import.is_folder(types):
            raise ValueError(paste_import.FOLDER_MESSAGE)
        uti = paste_import.file_type(types, has_text)
        if uti is not None:
            return ("file", str(await _load_file(providers[0], uti, into)))
    if has_text:
        text = pasteboard.string
        if text is not None and str(text):
            return ("text", str(text))
    return None
