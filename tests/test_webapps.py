"""Static web apps: detection, scanning and the localhost server."""

from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest

from mypystub import row_info, scan, webapps


def make(tmp_path: Path) -> Path:
    app = tmp_path / "site"
    app.mkdir()
    (app / "index.html").write_text(
        "<html><head><title> My  Site </title>"
        '<meta name="description" content="A demo"></head></html>'
    )
    (app / "a.txt").write_text("hello")
    (tmp_path / "secret.txt").write_text("nope")
    return app


def test_scan_finds_folder_and_page(tmp_path: Path) -> None:
    make(tmp_path)
    (tmp_path / "solo.html").write_text("<title>Solo</title>")
    rows = {r["title"]: r for r in scan.scan_all_prototypes(tmp_path)}
    assert rows["site"]["kind"] == "web"
    assert rows["site"]["subtitle"] == "A demo"
    assert rows["solo"]["kind"] == "web"
    assert rows["solo"]["subtitle"] == "Solo"
    assert rows["solo"]["web_page"] == "solo.html"


def test_pyproject_folder_is_still_a_project(tmp_path: Path) -> None:
    app = make(tmp_path)
    assert webapps.is_web_folder(app)
    (app / "pyproject.toml").write_text("[project]\nname='x'\nversion='1'\n")
    assert not webapps.is_web_folder(app)


def test_row_type() -> None:
    class Row:
        kind = "web"

    assert row_info.row_type(Row()) == "web"
    assert not row_info.runnable("web")


def test_server_serves_and_stays_inside(tmp_path: Path) -> None:
    app = make(tmp_path)
    server = webapps.StaticServer(app)
    url = server.start()
    try:
        assert b"My  Site" in urlopen(url).read()
        assert urlopen(url.replace("index.html", "a.txt")).read() == b"hello"
        with pytest.raises(URLError):
            urlopen(url.replace("index.html", "../secret.txt")).read()
    finally:
        server.stop()
