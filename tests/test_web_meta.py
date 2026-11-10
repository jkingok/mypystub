"""Reading a web app's title, description and icon (#150). No Toga needed."""

import base64
import io
import json
from pathlib import Path

import pytest

from mypystub import web_meta, webapps

PIL = pytest.importorskip("PIL.Image")


def png_bytes(size: int = 64, fmt: str = "PNG") -> bytes:
    out = io.BytesIO()
    PIL.new("RGB", (size, size), "red").save(out, fmt)
    return out.getvalue()


PAGE = """<!doctype html><html><head>
<title> Tip  Calc </title>
<meta name="description" content="Works out tips">
<meta property="og:title" content="Tipper">
<meta name="author" content="Pat">
<link rel="icon" href="icons/small.png" sizes="16x16">
<link rel="apple-touch-icon" href="/icons/big.png" sizes="180x180">
<link rel="manifest" href="app.webmanifest">
</head></html>"""


def test_page_metadata() -> None:
    meta = web_meta.parse_page(PAGE)
    assert meta.title == "Tip Calc" and meta.description == "Works out tips"
    assert meta.app_title == "Tipper" and meta.author == "Pat"
    assert meta.manifest == "app.webmanifest"
    assert ("icons/small.png", 16) in meta.icons and (
        "/icons/big.png",
        180,
    ) in meta.icons


def test_open_graph_description_is_a_fallback() -> None:
    meta = web_meta.parse_page('<meta property="og:description" content="OG">')
    assert meta.description == "OG"
    both = web_meta.parse_page(
        '<meta property="og:description" content="OG">'
        '<meta name="description" content="Plain">'
    )
    assert both.description == "Plain"


def test_manifest_wins_for_name_and_description() -> None:
    meta = web_meta.parse_page(PAGE)
    manifest = web_meta.parse_manifest(
        json.dumps({"name": "Tip Calculator", "description": "From manifest"})
    )
    assert web_meta.display_title(meta, manifest) == "Tip Calculator"
    assert web_meta.display_description(meta, manifest) == "From manifest"
    assert web_meta.display_title(meta, None) == "Tipper"
    assert (
        web_meta.parse_manifest("[1]") is None and web_meta.parse_manifest("x") is None
    )


@pytest.mark.parametrize(
    ("href", "base", "expected"),
    [
        ("icon.png", "", "icon.png"),
        ("/img/icon.png", "sub", "img/icon.png"),
        ("icon.png?v=2#x", "sub", "sub/icon.png"),
        ("../up.png", "sub", "up.png"),
        ("../../out.png", "sub", None),
        ("javascript:alert(1)", "", None),
        ("//cdn.example/i.png", "", "https://cdn.example/i.png"),
        ("https://x/i.png", "sub", "https://x/i.png"),
    ],
)
def test_resolve_ref(href: str, base: str, expected: str | None) -> None:
    assert web_meta.resolve_ref(href, base) == expected


def test_candidates_prefer_the_manifest_then_larger_then_favicon(
    tmp_path: Path,
) -> None:
    (tmp_path / "app.webmanifest").write_text(
        json.dumps({"icons": [{"src": "m/192.png", "sizes": "192x192"}]})
    )
    meta = web_meta.parse_page(PAGE)
    manifest = web_meta.load_manifest(tmp_path, meta)
    refs = [r.href for r in web_meta.icon_candidates(meta, manifest)]
    assert refs == ["m/192.png", "icons/big.png", "icons/small.png", "favicon.ico"]


def test_an_svg_ranks_as_the_largest() -> None:
    meta = web_meta.parse_page(
        '<link rel="icon" href="a.svg"><link rel="icon" href="b.png" sizes="192x192">'
    )
    refs = [r.href for r in web_meta.icon_candidates(meta, None)]
    assert refs == ["a.svg", "b.png", "favicon.ico"]


def test_a_local_jpeg_is_converted_to_png(tmp_path: Path) -> None:
    (tmp_path / "icon.jpg").write_bytes(png_bytes(200, "JPEG"))
    cache = tmp_path / "cache"
    icon, pending = web_meta.resolve_icon(
        tmp_path, [web_meta.IconRef("icon.jpg")], cache
    )
    assert icon is not None and pending == []
    with PIL.open(icon) as image:
        assert image.format == "PNG" and max(image.size) <= web_meta.ICON_PIXELS


def test_favicon_ico_is_found_by_default(tmp_path: Path) -> None:
    (tmp_path / "favicon.ico").write_bytes(png_bytes(32, "ICO"))
    meta = web_meta.parse_page("<title>x</title>")
    icon, _ = web_meta.resolve_icon(
        tmp_path, web_meta.icon_candidates(meta, None), tmp_path / "cache"
    )
    assert icon is not None and icon.suffix == ".png"


def test_data_urls_are_decoded(tmp_path: Path) -> None:
    url = "data:image/png;base64," + base64.b64encode(png_bytes()).decode()
    icon, _ = web_meta.resolve_icon(tmp_path, [web_meta.IconRef(url)], tmp_path / "c")
    assert icon is not None and icon.exists()


def test_paths_outside_the_app_are_refused(tmp_path: Path) -> None:
    (tmp_path / "secret.png").write_bytes(png_bytes())
    app = tmp_path / "app"
    app.mkdir()
    icon, _ = web_meta.resolve_icon(
        app, [web_meta.IconRef("../secret.png")], tmp_path / "c"
    )
    assert icon is None


Response = io.BytesIO  # supports `with`, like a urlopen response


def test_online_icons_are_fetched_once_then_used(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    url = "https://example.test/i.png"
    refs = [web_meta.IconRef(url)]
    icon, pending = web_meta.resolve_icon(tmp_path, refs, cache)
    assert icon is None and pending == [url]
    assert web_meta.fetch_remote(
        url, cache, opener=lambda r, timeout: Response(png_bytes())
    )
    icon, pending = web_meta.resolve_icon(tmp_path, refs, cache)
    assert icon is not None and pending == []


def test_a_failed_fetch_is_not_retried(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    url = "https://example.test/gone.png"

    def broken(request: object, timeout: float) -> Response:
        raise OSError("offline")

    assert not web_meta.fetch_remote(url, cache, opener=broken)
    _, pending = web_meta.resolve_icon(tmp_path, [web_meta.IconRef(url)], cache)
    assert pending == []


def test_the_row_uses_the_icon_and_description(tmp_path: Path) -> None:
    app = tmp_path / "site"
    app.mkdir()
    (app / "index.html").write_text(PAGE)
    (app / "app.webmanifest").write_text(json.dumps({"description": "Manifest says"}))
    (app / "icons").mkdir()
    (app / "icons" / "big.png").write_bytes(png_bytes(180))
    row = webapps.scan_web(app, tmp_path / "cache")
    assert row["subtitle"] == "Manifest says"
    assert row["icon_path"] is not None and row["icon_pending"] == []


def test_a_local_svg_icon_is_rasterised(tmp_path: Path) -> None:
    (tmp_path / "icon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
        '<circle cx="5" cy="5" r="4" fill="#00f"/></svg>'
    )
    icon, _ = web_meta.resolve_icon(
        tmp_path, [web_meta.IconRef("icon.svg")], tmp_path / "cache"
    )
    assert icon is not None
    with PIL.open(icon) as image:
        assert image.getpixel((image.width // 2, image.height // 2))[:3] == (0, 0, 255)


def test_an_svg_data_url_is_rasterised(tmp_path: Path) -> None:
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"><rect width="4" height="4" fill="red"/></svg>'
    url = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
    icon, _ = web_meta.resolve_icon(tmp_path, [web_meta.IconRef(url)], tmp_path / "c")
    assert icon is not None


SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
    '<circle cx="5" cy="5" r="4" fill="#00f"/></svg>'
)


def test_a_local_svg_icon_is_drawn_when_resvg_is_there(tmp_path: Path) -> None:
    pytest.importorskip("resvg_py")
    (tmp_path / "icon.svg").write_text(SVG)
    icon, _ = web_meta.resolve_icon(
        tmp_path, [web_meta.IconRef("icon.svg")], tmp_path / "cache"
    )
    assert icon is not None
    with PIL.open(icon) as image:
        assert image.format == "PNG"
        assert image.getpixel((image.width // 2, image.height // 2))[:3] == (0, 0, 255)


def test_an_svg_data_url_is_drawn(tmp_path: Path) -> None:
    pytest.importorskip("resvg_py")
    url = "data:image/svg+xml;base64," + base64.b64encode(SVG.encode()).decode()
    icon, _ = web_meta.resolve_icon(tmp_path, [web_meta.IconRef(url)], tmp_path / "c")
    assert icon is not None


def test_without_resvg_an_svg_is_skipped_for_the_next_icon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(__import__("sys").modules, "resvg_py", None)  # not importable
    (tmp_path / "icon.svg").write_text(SVG)
    (tmp_path / "fallback.png").write_bytes(png_bytes())
    refs = [web_meta.IconRef("icon.svg"), web_meta.IconRef("fallback.png")]
    icon, _ = web_meta.resolve_icon(tmp_path, refs, tmp_path / "cache")
    assert icon is not None and web_meta.svg_to_png(SVG.encode()) is None


@pytest.mark.parametrize(
    "svg",
    [
        '<svg xmlns="http://www.w3.org/2000/svg"><image href="/etc/passwd"/></svg>',
        '<svg xmlns:x="http://www.w3.org/1999/xlink"><image x:href="file:///x.png"/></svg>',
        '<svg><IMAGE HREF="https://example.test/a.png"/></svg>',
        '<!DOCTYPE svg [<!ENTITY a "b">]><svg xmlns="http://www.w3.org/2000/svg"/>',
    ],
)
def test_svgs_that_reach_outside_themselves_are_refused(svg: str) -> None:
    assert not web_meta.svg_is_self_contained(svg.encode())
    assert web_meta.svg_to_png(svg.encode()) is None


def test_an_embedded_data_image_is_allowed() -> None:
    svg = '<svg><image href="data:image/png;base64,AAAA"/></svg>'
    assert web_meta.svg_is_self_contained(svg.encode())


def test_garbage_is_not_an_svg() -> None:
    assert not web_meta.looks_like_svg(b"\x89PNG\r\n\x1a\n")
    assert web_meta.looks_like_svg(b'<?xml version="1.0"?>\n<svg/>')
    pytest.importorskip("resvg_py")
    assert web_meta.svg_to_png(b"<svg><broken") is None
