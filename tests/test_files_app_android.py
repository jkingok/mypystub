"""Opening the documents on Android, through the app's own provider (#214).

Chaquopy's classes are replaced by stand-ins that record the intents started.
"""

from pathlib import Path
from typing import Any

import pytest

from mypystub import files_app

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "android" / "java"
PROVIDER = ASSETS / "au" / "id" / "jking" / "mypystub" / "AppDocumentsProvider.java"
PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


class Intent:
    """Records what is set on an android.content.Intent."""

    ACTION_VIEW = "android.intent.action.VIEW"
    ACTION_OPEN_DOCUMENT = "android.intent.action.OPEN_DOCUMENT"
    CATEGORY_OPENABLE = "android.intent.category.OPENABLE"
    FLAG_GRANT_READ_URI_PERMISSION = 1

    def __init__(self, action: str) -> None:
        self.action = action
        self.data: Any = None
        self.type: str | None = None
        self.extras: dict[str, Any] = {}
        self.categories: list[str] = []
        self.flags = 0

    def setDataAndType(self, data: Any, kind: str) -> None:
        self.data, self.type = data, kind

    def setType(self, kind: str) -> None:
        self.type = kind

    def addFlags(self, flags: int) -> None:
        self.flags |= flags

    def addCategory(self, category: str) -> None:
        self.categories.append(category)

    def putExtra(self, name: str, value: Any) -> None:
        self.extras[name] = value


class Contract:
    """android.provider.DocumentsContract, building readable stand-in URIs."""

    EXTRA_INITIAL_URI = "android.provider.extra.INITIAL_URI"

    @staticmethod
    def buildRootUri(authority: str, root: str) -> str:
        return f"content://{authority}/root/{root}"

    @staticmethod
    def buildDocumentUri(authority: str, document: str) -> str:
        return f"content://{authority}/document/{document}"


class Activity:
    def __init__(self, refuse: int = 0) -> None:
        self.started: list[Intent] = []
        self.refuse = refuse  # how many startActivity calls fail first

    def startActivity(self, intent: Intent) -> None:
        if self.refuse:
            self.refuse -= 1
            raise RuntimeError("ActivityNotFoundException: No Activity found")
        self.started.append(intent)


def jclass_for(activity: Activity) -> Any:
    classes = {
        "org.beeware.android.MainActivity": type("M", (), {"singletonThis": activity}),
        "android.content.Intent": Intent,
        "android.provider.DocumentsContract": Contract,
    }
    return classes.__getitem__


def test_the_provider_root_is_viewed_first() -> None:
    activity = Activity()
    assert files_app.open_android_files(jclass_for(activity)) is True
    (intent,) = activity.started
    assert intent.action == Intent.ACTION_VIEW
    assert intent.data == "content://au.id.jking.mypystub.documents/root/mypystub"
    assert intent.type == "vnd.android.document/root"


def test_the_picker_at_the_root_when_nothing_views_it() -> None:
    activity = Activity(refuse=1)
    assert files_app.open_android_files(jclass_for(activity)) is True
    (intent,) = activity.started
    assert intent.action == Intent.ACTION_OPEN_DOCUMENT
    assert intent.extras[Contract.EXTRA_INITIAL_URI] == (
        "content://au.id.jking.mypystub.documents/document/root"
    )
    assert intent.categories == [Intent.CATEGORY_OPENABLE]


def test_false_when_neither_starts() -> None:
    assert files_app.open_android_files(jclass_for(Activity(refuse=2))) is False


def test_without_chaquopy_it_says_it_could_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(files_app.sys, "platform", "android")
    assert files_app.open_in_files(tmp_path) is False


def test_the_ids_match_the_provider_and_the_manifest() -> None:
    """The authority and root IDs are written in three places; keep them equal."""
    java = PROVIDER.read_text(encoding="utf-8")
    assert f'AUTHORITY = "{files_app.ANDROID_AUTHORITY}"' in java
    assert f'ROOT_ID = "{files_app.ANDROID_ROOT_ID}"' in java
    assert f'ROOT_DOC_ID = "{files_app.ANDROID_ROOT_DOCUMENT}"' in java
    manifest = PYPROJECT.read_text(encoding="utf-8")
    assert f'android:authorities="{files_app.ANDROID_AUTHORITY}"' in manifest


def test_the_provider_implements_every_flag_it_advertises() -> None:
    """Android's defaults throw for these; advertising one unimplemented crashes
    the file browser that calls it."""
    java = PROVIDER.read_text(encoding="utf-8")
    needed = {
        "FLAG_SUPPORTS_SEARCH": "querySearchDocuments",
        "FLAG_SUPPORTS_IS_CHILD": "isChildDocument",
        "FLAG_SUPPORTS_RENAME": "renameDocument",
        "FLAG_SUPPORTS_COPY": "copyDocument",
        "FLAG_SUPPORTS_MOVE": "moveDocument",
        "FLAG_SUPPORTS_DELETE": "deleteDocument",
        "FLAG_SUPPORTS_CREATE": "createDocument",
        "FLAG_SUPPORTS_REMOVE": "removeDocument",
        "FLAG_SUPPORTS_RECENTS": "queryRecentDocuments",
    }
    missing = [
        flag
        for flag, method in needed.items()
        if flag in java and f" {method}(" not in java
    ]
    assert not missing, missing
