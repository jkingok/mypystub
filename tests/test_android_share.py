"""Android's share sheet through the app's documents provider (#217)."""

from pathlib import Path

import pytest

from mypystub import android_share, share_items
from tests.support_android_share import Java


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


def test_the_content_uri_comes_from_the_documents_provider(
    folders: tuple[Path, Path],
) -> None:
    files, cache = folders
    report = cache / "about.txt"
    report.write_text("details")
    uri = android_share.content_uri(Java(files, cache).jclass, report)
    assert uri == "content://au.id.jking.mypystub.documents/document/share/about.txt"
    assert (cache / "share" / "about.txt").read_text() == "details"


def test_the_ids_match_the_provider() -> None:
    """The Java provider and this module agree on the share prefix and folder."""
    java = (
        Path(__file__).parent.parent
        / "assets/android/java/au/id/jking/mypystub/AppDocumentsProvider.java"
    ).read_text()
    assert f'SHARE_PREFIX = "{android_share.SHARE_PREFIX}"' in java
    assert f'getCacheDir(), "{share_items.SHARE_FOLDER}"' in java
