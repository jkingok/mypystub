"""Stand-ins for Chaquopy's Android classes that sharing uses (#217, #323)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class Java:
    """Stand-ins for the Chaquopy classes sharing uses, recording calls."""

    def __init__(self, files: Path, cache: Path) -> None:
        self.started: list[Any] = []
        java = self

        class Folder:
            def __init__(self, path: Path) -> None:
                self.path = path

            def getAbsolutePath(self) -> str:
                return str(self.path)

        class Activity:
            def getFilesDir(self) -> Folder:
                return Folder(files)

            def getCacheDir(self) -> Folder:
                return Folder(cache)

            def getPackageName(self) -> str:
                return "au.id.jking.mypystub"

            def startActivity(self, intent: Any) -> None:
                java.started.append(intent)

        class MainActivity:
            singletonThis = Activity()

        class Intent:
            ACTION_SEND = "SEND"
            EXTRA_STREAM = "STREAM"
            EXTRA_SUBJECT = "SUBJECT"
            EXTRA_TEXT = "TEXT"
            FLAG_GRANT_READ_URI_PERMISSION = 1

            def __init__(self, action: str) -> None:
                self.action, self.extras, self.flags = action, {}, 0
                self.type = self.clip = self.target = self.title = None

            def setType(self, kind: str) -> None:
                self.type = kind

            def putExtra(self, key: str, value: Any) -> None:
                self.extras[key] = value

            def setClipData(self, clip: Any) -> None:
                self.clip = clip

            def addFlags(self, flags: int) -> None:
                self.flags |= flags

            @staticmethod
            def createChooser(target: Intent, title: str) -> Intent:
                chooser = Intent("CHOOSER")
                chooser.target, chooser.title = target, title
                return chooser

        class DocumentsContract:
            @staticmethod
            def buildDocumentUri(authority: str, doc: str) -> str:
                return f"content://{authority}/document/{doc}"

        class ClipData:
            @staticmethod
            def newRawUri(label: str, uri: str) -> tuple[str, str]:
                return (label, uri)

        self.classes = {
            "org.beeware.android.MainActivity": MainActivity,
            "android.content.Intent": Intent,
            "android.provider.DocumentsContract": DocumentsContract,
            "android.content.ClipData": ClipData,
        }

    def jclass(self, name: str) -> Any:
        return self.classes[name]
