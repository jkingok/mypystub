"""Android's share sheet, for everything the app shares out (#217).

Share (a script, project or zipapp), Backup, About's environment details and
Share source code all hand a file to :func:`share_file`. It starts Android's
chooser with an ``ACTION_SEND`` intent whose ``content://`` URI comes from the
app's own documents provider (AppDocumentsProvider), with read permission
granted to the app the user picks:

- a file in Documents is shared as it is, by its document ID ``root/<path>``;
- anything else (the cache, where backups and zips are made) is copied into the
  cache's ``share/`` folder first, and shared as ``share/<name>``, which the
  provider serves read-only and never lists.

Importing ``java`` happens in :func:`share_file`'s caller, so this module is
tested on desktop with stand-ins for Chaquopy's classes. Sharing into the app
(import) isn't handled here; Paste does that.
"""

from __future__ import annotations

import mimetypes
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .files_app import ANDROID_ROOT_DOCUMENT, AUTHORITY_SUFFIX
from .share_items import SHARE_FOLDER

SHARE_PREFIX = f"{SHARE_FOLDER}/"  # AppDocumentsProvider.SHARE_PREFIX
# Types Android apps recognise better than the generic one
EXTRA_TYPES = {".py": "text/x-python", ".pyz": "application/zip"}


def mime_type(path: Path) -> str:
    """The MIME type to announce for `path`."""
    known = EXTRA_TYPES.get(path.suffix.lower())
    return known or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def document_id(path: Path, files_dir: Path, cache_dir: Path) -> str:
    """The provider's ID for `path`, copying it to the share folder if needed.

    `files_dir` is the folder the provider shows (Documents), `cache_dir` the
    app's cache, whose ``share/`` folder the provider serves read-only.
    """
    path = path.resolve()
    if path.is_relative_to(files_dir.resolve()):
        relative = path.relative_to(files_dir.resolve()).as_posix()
        return f"{ANDROID_ROOT_DOCUMENT}/{relative}"
    share = (cache_dir / SHARE_FOLDER).resolve()
    if path.parent != share:
        share.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, share / path.name)
    return SHARE_PREFIX + path.name


def share_file(jclass: Callable[[str], Any], path: Path, title: str = "Share") -> None:
    """Show Android's share sheet for `path`.

    `jclass` is Chaquopy's ``java.jclass``. Must run on the main thread, as
    button handlers do.
    """
    if not path.is_file():
        raise FileNotFoundError(f"{path} isn't there any more.")
    activity = jclass("org.beeware.android.MainActivity").singletonThis
    intent_class = jclass("android.content.Intent")
    contract = jclass("android.provider.DocumentsContract")
    clip_data = jclass("android.content.ClipData")

    files_dir = Path(str(activity.getFilesDir().getAbsolutePath()))
    cache_dir = Path(str(activity.getCacheDir().getAbsolutePath()))
    authority = str(activity.getPackageName()) + AUTHORITY_SUFFIX
    uri = contract.buildDocumentUri(authority, document_id(path, files_dir, cache_dir))

    send = intent_class(intent_class.ACTION_SEND)
    send.setType(mime_type(path))
    send.putExtra(intent_class.EXTRA_STREAM, uri)
    send.putExtra(intent_class.EXTRA_SUBJECT, path.name)
    # The ClipData carries the grant through the chooser to the chosen app
    send.setClipData(clip_data.newRawUri(path.name, uri))
    send.addFlags(intent_class.FLAG_GRANT_READ_URI_PERMISSION)
    chooser = intent_class.createChooser(send, title)
    chooser.addFlags(intent_class.FLAG_GRANT_READ_URI_PERMISSION)
    activity.startActivity(chooser)
