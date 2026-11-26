"""The content URI Android's share sheet sends for a file (#217).

Share (a script, project or zipapp), Backup, About's environment details, Share
source code and the Logs tab all share through ``togax_jkingok.share``. On
Android another app can read a file only through a content URI, which
:func:`content_uri` makes with the app's own documents provider
(AppDocumentsProvider):

- a file in Documents is shared as it is, by its document ID ``root/<path>``;
- anything else (the cache, where backups and zips are made) is copied into the
  cache's ``share/`` folder first, and shared as ``share/<name>``, which the
  provider serves read-only and never lists.

Importing ``java`` happens in the caller, so this module is tested on desktop
with stand-ins for Chaquopy's classes. Sharing into the app (import) isn't
handled here; Paste does that.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .files_app import ANDROID_ROOT_DOCUMENT, AUTHORITY_SUFFIX
from .share_items import SHARE_FOLDER

SHARE_PREFIX = f"{SHARE_FOLDER}/"  # AppDocumentsProvider.SHARE_PREFIX


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


def content_uri(jclass: Callable[[str], Any], path: Path) -> Any:
    """The provider's ``content://`` URI for `path`; `jclass` is Chaquopy's."""
    activity = jclass("org.beeware.android.MainActivity").singletonThis
    contract = jclass("android.provider.DocumentsContract")
    files_dir = Path(str(activity.getFilesDir().getAbsolutePath()))
    cache_dir = Path(str(activity.getCacheDir().getAbsolutePath()))
    authority = str(activity.getPackageName()) + AUTHORITY_SUFFIX
    return contract.buildDocumentUri(authority, document_id(path, files_dir, cache_dir))
