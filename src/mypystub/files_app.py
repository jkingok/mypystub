"""Open the Files app at one of this app's folders (#181).

On iOS the ``shareddocuments://`` scheme, followed by a folder's path, opens
Files at that folder. It works because the app shares its Documents folder
(``UIFileSharingEnabled`` and ``LSSupportsOpeningDocumentsInPlace``). A device
test found the plain path works, as does the folder as a ``file://`` URL, and
that the scheme alone only opens Files wherever it was last.

On Android the app's documents live in private storage, which no other app can
open by path. They are shown through the app's own DocumentsProvider
(``assets/android/java/.../AppDocumentsProvider.java``), so the button asks the
system Files browser to open the provider's root, and, where nothing handles
that, opens the system file picker at it instead (#214).

The URL is built here, free of Toga, so it can be unit tested on desktop.
"""

from __future__ import annotations

import sys
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote

SCHEME = "shareddocuments://"

# Must match android:authorities in pyproject.toml and AppDocumentsProvider.java
ANDROID_AUTHORITY = "au.id.jking.mypystub.documents"
ANDROID_ROOT_ID = "mypystub"  # AppDocumentsProvider.ROOT_ID
ANDROID_ROOT_DOCUMENT = "root"  # AppDocumentsProvider.ROOT_DOC_ID
# DocumentsContract.Root.MIME_TYPE_ITEM: "this URI is a root, open it to browse"
ANDROID_ROOT_MIME = "vnd.android.document/root"


def files_url(folder: Path) -> str:
    """The URL that opens the Files app at `folder`."""
    return SCHEME + quote(str(folder))


def open_android_files(jclass: Callable[[str], Any]) -> bool:
    """Open the app's documents in the system Files browser on Android.

    `jclass` is Chaquopy's ``java.jclass``, passed in so this can be tested with
    stand-ins. First a view of the provider's root, which the system Files app
    handles; if nothing does, the system file picker opened at the root, where
    the files can be browsed, opened and shared too. False if neither started.
    """
    # Briefcase's MainActivity keeps itself in a static field
    activity = jclass("org.beeware.android.MainActivity").singletonThis
    intent_class = jclass("android.content.Intent")
    contract = jclass("android.provider.DocumentsContract")

    view = intent_class(intent_class.ACTION_VIEW)
    view.setDataAndType(
        contract.buildRootUri(ANDROID_AUTHORITY, ANDROID_ROOT_ID), ANDROID_ROOT_MIME
    )
    view.addFlags(intent_class.FLAG_GRANT_READ_URI_PERMISSION)
    try:
        activity.startActivity(view)
        return True
    except Exception as error:  # noqa: BLE001  (ActivityNotFoundException, ...)
        print(f"Viewing the documents root failed ({error}); opening the picker")

    pick = intent_class(intent_class.ACTION_OPEN_DOCUMENT)
    pick.addCategory(intent_class.CATEGORY_OPENABLE)
    pick.setType("*/*")
    pick.putExtra(
        contract.EXTRA_INITIAL_URI,
        contract.buildDocumentUri(ANDROID_AUTHORITY, ANDROID_ROOT_DOCUMENT),
    )
    try:
        activity.startActivity(pick)
        return True
    except Exception as error:  # noqa: BLE001
        print(f"Opening the file picker failed: {error}")
        return False


def open_in_files(folder: Path) -> bool:
    """Open `folder` in the Files app, or the system's file browser elsewhere.

    Returns False if it couldn't be opened. On iOS this must be called on the
    main thread, as button handlers are. On Android `folder` is always the app's
    documents folder, which is what its provider shows.
    """
    if sys.platform == "android":
        try:
            from java import jclass  # type: ignore[import-not-found]  # Chaquopy
        except ImportError:
            return False
        return open_android_files(jclass)
    if sys.platform == "ios":
        from toga_iOS.libs import NSURL  # pyright: ignore[reportMissingImports]

        from .bridge import shared_application

        url = NSURL.URLWithString_(files_url(folder))
        shared_application().openURL_options_completionHandler_(url, {}, None)
        return True
    return bool(webbrowser.open(folder.as_uri()))
