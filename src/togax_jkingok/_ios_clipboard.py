"""iOS's pasteboard (iOS only; see clipboard).

toga_iOS doesn't declare ``UIPasteboard``, so it's looked up here, once: the
package's only ``ObjCClass`` for it. On other platforms the module imports and
defines nothing usable.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from . import clipboard

if sys.platform == "ios":
    from rubicon.objc import ObjCClass  # pyright: ignore[reportMissingImports]

    UIPasteboard: Any = ObjCClass("UIPasteboard")
else:
    UIPasteboard: Any = None  # iOS only

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
                path = clipboard.keep_copy(source, into)
            elif error:
                message = str(ObjCInstance(error).localizedDescription)
                problem = OSError(f"{message}. If iOS asks, choose Allow Paste.")
        except OSError as failure:
            problem = failure
        loop.call_soon_threadsafe(deliver, path, problem)

    block = Block(finished, None, objc_id, objc_id)
    provider.loadFileRepresentationForTypeIdentifier(uti, completionHandler=block)
    try:
        return await asyncio.wait_for(loaded, clipboard.PASTE_TIMEOUT)
    except TimeoutError:
        _abandoned_blocks.append(block)
        raise OSError("The copied file took too long to arrive.") from None


async def read(into: Path) -> clipboard.Text | clipboard.File | None:
    """The pasteboard's file (preferred) or text; see clipboard.read.

    A file URL lives outside the app, so its security-scoped access is started
    here and left open for the copy that follows; the system reclaims it when
    the app quits.
    """
    pasteboard = UIPasteboard.generalPasteboard
    if pasteboard.hasURLs:
        url = pasteboard.URL
        if url is not None and url.isFileURL:
            url.startAccessingSecurityScopedResource()
            return clipboard.File(Path(str(url.path)))
    has_text = bool(pasteboard.hasStrings)
    providers = list(pasteboard.itemProviders)
    if providers:  # only the first of several copied files
        types = [str(uti) for uti in providers[0].registeredTypeIdentifiers]
        if clipboard.is_folder(types):
            raise ValueError(clipboard.FOLDER_MESSAGE)
        uti = clipboard.file_type(types, has_text)
        if uti is not None:
            return clipboard.File(await _load_file(providers[0], uti, into))
    if has_text:
        text = pasteboard.string
        if text is not None and str(text):
            return clipboard.Text(str(text))
    return None


def write_text(text: str) -> bool:
    """Replace the pasteboard's contents with `text`."""
    UIPasteboard.generalPasteboard.string = text
    return True


def suggested_name() -> str | None:
    """The name the copying app gave the pasteboard's first item, if any."""
    providers = list(UIPasteboard.generalPasteboard.itemProviders)
    name = providers[0].suggestedName if providers else None
    return str(name) if name else None
