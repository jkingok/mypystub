"""Opening the Files app at a folder (#181)."""

from pathlib import Path

import pytest

from mypystub import files_app


def test_the_url_is_the_scheme_and_the_encoded_path() -> None:
    """The form a device test found works: shareddocuments:// + the folder path."""
    folder = Path("/var/mobile/Containers/Data/Application/ABC/Documents")
    assert files_app.files_url(folder) == (
        "shareddocuments:///var/mobile/Containers/Data/Application/ABC/Documents"
    )


def test_spaces_and_non_ascii_are_encoded() -> None:
    """Characters a URL can't hold are percent-encoded."""
    url = files_app.files_url(Path("/data/My App/café"))
    assert url == "shareddocuments:///data/My%20App/caf%C3%A9"


def test_off_ios_the_system_file_browser_is_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On the desktop the folder opens in whatever shows folders."""
    opened: list[str] = []
    monkeypatch.setattr(
        files_app.webbrowser, "open", lambda url: opened.append(url) or True
    )
    assert files_app.open_in_files(tmp_path) is True
    assert opened == [tmp_path.as_uri()]


def test_a_failure_to_open_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """False comes back, for the caller to say so."""
    monkeypatch.setattr(files_app.webbrowser, "open", lambda url: False)
    assert files_app.open_in_files(tmp_path) is False
