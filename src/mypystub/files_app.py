"""Open the Files app at one of this app's folders (#181).

On iOS the ``shareddocuments://`` scheme, followed by a folder's path, opens
Files at that folder. It works because the app shares its Documents folder
(``UIFileSharingEnabled`` and ``LSSupportsOpeningDocumentsInPlace``). A device
test found the plain path works, as does the folder as a ``file://`` URL, and
that the scheme alone only opens Files wherever it was last.

The URL is built here, free of Toga, so it can be unit tested on desktop.
"""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path
from urllib.parse import quote

SCHEME = "shareddocuments://"


def files_url(folder: Path) -> str:
    """The URL that opens the Files app at `folder`."""
    return SCHEME + quote(str(folder))


def open_in_files(folder: Path) -> bool:
    """Open `folder` in the Files app, or the system's file browser off iOS.

    Returns False if it couldn't be opened. On iOS this must be called on the
    main thread, as button handlers are.
    """
    if sys.platform == "ios":
        from toga_iOS.libs import NSURL  # pyright: ignore[reportMissingImports]

        from .bridge import shared_application

        url = NSURL.URLWithString_(files_url(folder))
        shared_application().openURL_options_completionHandler_(url, {}, None)
        return True
    return bool(webbrowser.open(folder.as_uri()))
