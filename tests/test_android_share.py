"""Android's share sheet through the app's documents provider (#217)."""

from pathlib import Path
from typing import Any

import pytest

from mypystub import android_share, share_items


@pytest.fixture
def folders(tmp_path: Path) -> tuple[Path, Path]:
    """The provider's documents folder and the app's cache."""
    files, cache = tmp_path / "files", tmp_path / "cache"
    files.mkdir()
    cache.mkdir()
    return files, cache


def test_a_document_is_shared_where_it_is(folders: tuple[Path, Path]) -> None:
    files, cache = folders
    script = files / "tools" / "tip.py"
    script.parent.mkdir()
    script.write_text("print(1)")
    assert android_share.document_id(script, files, cache) == "root/tools/tip.py"
    assert not (cache / "share").exists()  # nothing copied


def test_anything_else_is_copied_to_the_share_folder(
    folders: tuple[Path, Path],
) -> None:
    files, cache = folders
    backup = cache / "backup.zip"
    backup.write_bytes(b"PK")
    assert android_share.document_id(backup, files, cache) == "share/backup.zip"
    assert (cache / "share" / "backup.zip").read_bytes() == b"PK"


def test_a_project_zip_already_staged_isnt_copied_again(
    folders: tuple[Path, Path],
) -> None:
    files, cache = folders
    project = files / "weather"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='w'\n")
    staged = share_items.prepare_share(project, cache)
    assert staged.parent == cache / "share"
    before = staged.stat().st_mtime_ns
    assert android_share.document_id(staged, files, cache) == "share/weather.zip"
    assert staged.stat().st_mtime_ns == before


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("tip.py", "text/x-python"),
        ("app.pyz", "application/zip"),
        ("backup.zip", "application/zip"),
        ("about.txt", "text/plain"),
        ("data.unknownext", "application/octet-stream"),
    ],
)
def test_mime_types(name: str, kind: str) -> None:
    assert android_share.mime_type(Path(name)) == kind


class Java:
    """Stand-ins for the Chaquopy classes share_file uses, recording calls."""

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
            def createChooser(target: "Intent", title: str) -> "Intent":
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


def test_share_file_starts_a_chooser_with_a_granted_uri(
    folders: tuple[Path, Path],
) -> None:
    files, cache = folders
    report = cache / "about.txt"
    report.write_text("details")
    java = Java(files, cache)
    android_share.share_file(java.jclass, report)
    (chooser,) = java.started
    send = chooser.target
    uri = "content://au.id.jking.mypystub.documents/document/share/about.txt"
    assert chooser.action == "CHOOSER" and chooser.flags == 1
    assert send.action == "SEND" and send.type == "text/plain"
    assert send.extras == {"STREAM": uri, "SUBJECT": "about.txt"}
    assert send.clip == ("about.txt", uri) and send.flags == 1


def test_a_missing_file_says_so(folders: tuple[Path, Path]) -> None:
    files, cache = folders
    with pytest.raises(FileNotFoundError):
        android_share.share_file(Java(files, cache).jclass, files / "gone.py")


def test_sharing_is_offered_on_android(monkeypatch: pytest.MonkeyPatch) -> None:
    for platform, offered in (("ios", True), ("android", True), ("linux", False)):
        monkeypatch.setattr("sys.platform", platform)
        assert share_items.share_available() is offered


def test_the_ids_match_the_provider() -> None:
    """The Java provider and this module agree on the share prefix and folder."""
    java = (
        Path(__file__).parent.parent
        / "assets/android/java/au/id/jking/mypystub/AppDocumentsProvider.java"
    ).read_text()
    assert f'SHARE_PREFIX = "{android_share.SHARE_PREFIX}"' in java
    assert f'getCacheDir(), "{share_items.SHARE_FOLDER}"' in java
