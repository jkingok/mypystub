"""What a web app says about itself: title, description and icon (#150).

Read from the page's own markup the way a browser would: ``<title>``, the
``description``, ``og:`` and ``apple-mobile-web-app-title`` metas, ``<link
rel="icon">`` and its ``apple-touch-icon`` and ``manifest`` relatives, then a PWA
manifest's name, description and icons, and last the ``/favicon.ico`` a browser
tries when a page names no icon.

The launcher's list can't show every image format (JPEG isn't supported there,
PNG is preferred), so a chosen icon is converted to a small PNG in the cache.
Icons given as ``data:`` URLs are decoded; online ones are fetched (once, by
:func:`fetch_remote`) and then used from the cache. Pillow does the conversion
where it is installed; without it only a PNG is used as it is.

An SVG is drawn by ``resvg-py``, which binds resvg: a maintained Rust renderer,
rather than anything written here. It is optional: where it isn't installed
(there is no iOS wheel for it yet) an SVG is skipped and the next icon is used.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import posixpath
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

ICON_RELS = (
    "icon",
    "shortcut icon",
    "apple-touch-icon",
    "apple-touch-icon-precomposed",
)
MAX_ICON_BYTES = 2_000_000
ICON_PIXELS = 128  # the list shows icons small; this keeps the cache small too
FAVICON = "favicon.ico"
Opener = Any  # urlopen-like: opener(Request, timeout=...) -> file-like


@dataclass(frozen=True)
class IconRef:
    """An icon a page or manifest names: where it is and how big it says it is."""

    href: str  # a data: or http(s): URL, or a path inside the app, resolved
    size: int = 0  # longest edge in pixels; 0 when unstated


@dataclass
class PageMeta:
    """The well-known metadata of an HTML page."""

    title: str | None = None
    description: str | None = None
    author: str | None = None
    keywords: str | None = None
    theme_color: str | None = None
    app_title: str | None = None  # og:title, apple-mobile-web-app-title, ...
    canonical: str | None = None
    manifest: str | None = None
    icons: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class Manifest:
    """What a PWA ``manifest.json`` says."""

    name: str | None = None
    short_name: str | None = None
    description: str | None = None
    start_url: str | None = None
    display: str | None = None
    theme_color: str | None = None
    icons: list[tuple[str, int]] = field(default_factory=list)


def _clean(text: str | None) -> str | None:
    return " ".join(text.split()) or None if text else None


def _size(sizes: str | None) -> int:
    """The longest edge of a ``sizes`` attribute such as ``"32x32 64x64"``."""
    best = 0
    for part in (sizes or "").lower().split():
        if part == "any":
            best = max(best, 512)
        elif match := re.fullmatch(r"(\d+)x(\d+)", part):
            best = max(best, int(match[1]), int(match[2]))
    return best


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta = PageMeta()
        self._in_title = False
        self._title = ""
        self.og_description: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = (a.get("name") or a.get("property") or "").lower()
            content = _clean(a.get("content"))
            m = self.meta
            if name == "description":
                m.description = content
            elif name == "og:description":
                self.og_description = content
            elif name in ("og:title", "apple-mobile-web-app-title", "application-name"):
                m.app_title = m.app_title or content
            elif name == "author":
                m.author = content
            elif name == "keywords":
                m.keywords = content
            elif name == "theme-color":
                m.theme_color = content
        elif tag == "link":
            rels = " ".join(a.get("rel", "").lower().split())
            href = a.get("href", "").strip()
            if not href:
                return
            if rels == "manifest":
                self.meta.manifest = href
            elif rels == "canonical":
                self.meta.canonical = href
            elif rels in ICON_RELS:
                self.meta.icons.append((href, _size(a.get("sizes"))))

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._in_title:
            self._in_title = False
            self.meta.title = self.meta.title or _clean(self._title)


def parse_page(text: str) -> PageMeta:
    """The metadata in an HTML page (only its start is read: that's where it is)."""
    parser = _Parser()
    parser.feed(text[:100_000])
    parser.meta.description = parser.meta.description or parser.og_description
    return parser.meta


def parse_manifest(text: str) -> Manifest | None:
    """A PWA manifest's fields, or None if it isn't a JSON object."""
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None

    def string(key: str) -> str | None:
        value = data.get(key)
        return _clean(value) if isinstance(value, str) else None

    icons = [
        (str(icon["src"]), _size(icon.get("sizes")))
        for icon in data.get("icons", [])
        if isinstance(icon, dict) and icon.get("src")
    ]
    return Manifest(
        string("name"),
        string("short_name"),
        string("description"),
        string("start_url"),
        string("display"),
        string("theme_color"),
        icons,
    )


def display_title(meta: PageMeta, manifest: Manifest | None) -> str | None:
    """The app's own name for itself: manifest, then metas, then ``<title>``."""
    if manifest and (manifest.name or manifest.short_name):
        return manifest.name or manifest.short_name
    return meta.app_title or meta.title


def display_description(meta: PageMeta, manifest: Manifest | None) -> str | None:
    """Its description: the manifest's, else the page's."""
    return (manifest.description if manifest else None) or meta.description


# -- Locating files ----------------------------------------------------------------


def resolve_ref(href: str, base: str = "") -> str | None:
    """A reference as an absolute/data URL, or a path inside the app; None if unsafe.

    `base` is the folder (inside the app) of the file that made the reference.
    A path is ``/``-separated, without a leading ``/``, and never leaves the app.
    """
    href = href.strip()
    if href.startswith(("data:", "http://", "https://")):
        return href
    if href.startswith("//"):
        return "https:" + href
    if urlsplit(href).scheme:  # javascript:, file:, ...
        return None
    path = unquote(urlsplit(href).path)
    joined = path.lstrip("/") if path.startswith("/") else posixpath.join(base, path)
    normal = posixpath.normpath(joined)
    if normal in ("", ".") or normal.startswith(".."):
        return None
    return normal


def _read_local(root: Path, ref: str) -> bytes | None:
    path = (root / ref).resolve()
    try:
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            return None
        if path.stat().st_size > MAX_ICON_BYTES:
            return None
        return path.read_bytes()
    except OSError:
        return None


def decode_data_url(url: str) -> bytes | None:
    """The bytes of a ``data:`` URL, or None if it can't be read."""
    head, _, payload = url.partition(",")
    if not head.startswith("data:") or not payload:
        return None
    try:
        if head.endswith(";base64"):
            data = base64.b64decode(payload, validate=False)
        else:
            data = unquote(payload).encode("latin-1")
    except (ValueError, UnicodeEncodeError):
        return None
    return data if len(data) <= MAX_ICON_BYTES else None


def load_manifest(root: Path, meta: PageMeta) -> Manifest | None:
    """The page's manifest if it is a local file or a data URL (not an online one)."""
    if not meta.manifest:
        return None
    ref = resolve_ref(meta.manifest)
    if ref is None or ref.startswith(("http://", "https://")):
        return None
    raw = decode_data_url(ref) if ref.startswith("data:") else _read_local(root, ref)
    manifest = parse_manifest(raw.decode("utf-8", "replace")) if raw else None
    if manifest is None:
        return None
    # Icons in a manifest are relative to the manifest's own folder
    base = posixpath.dirname(ref) if not ref.startswith("data:") else ""
    manifest.icons = [
        (resolved, size)
        for src, size in manifest.icons
        if (resolved := resolve_ref(src, base)) is not None
    ]
    return manifest


def _scalable(href: str, size: int) -> int:
    """An icon's size for ranking: an SVG, which has none, is as big as can be."""
    is_svg = urlsplit(href).path.lower().endswith(".svg") or href.startswith(
        "data:image/svg"
    )
    return 4096 if is_svg else size


def icon_candidates(meta: PageMeta, manifest: Manifest | None) -> list[IconRef]:
    """Icons to try, best first: the manifest's, the page's, then ``favicon.ico``.

    Each group is largest first. An SVG scales to any size, so it counts as the
    largest (it is drawn if resvg is there, else the next icon is used).
    """
    groups = []
    if manifest:
        groups.append(manifest.icons)
    page = [
        (resolved, size)
        for href, size in meta.icons
        if (resolved := resolve_ref(href)) is not None
    ]
    groups.append(page)
    refs: list[IconRef] = []
    for group in groups:
        for href, size in sorted(group, key=lambda item: -_scalable(*item)):
            refs.append(IconRef(href, size))
    refs.append(IconRef(FAVICON))
    return refs


# -- Icons the list can show -------------------------------------------------------


# An <image> in an SVG may only carry its data: a link to a file is not followed
_IMAGE_TAG = re.compile(rb"<image\b[^>]*>", re.IGNORECASE | re.DOTALL)
_LINK = re.compile(rb"""href\s*=\s*["']\s*([^"']*)""", re.IGNORECASE)


def svg_is_self_contained(data: bytes) -> bool:
    """Whether an SVG is safe to hand to the renderer.

    No entity declarations, and no ``<image>`` that points at a file or a URL:
    rendering must not read anything but the SVG itself.
    """
    if b"<!ENTITY" in data:
        return False
    for tag in _IMAGE_TAG.findall(data):
        for link in _LINK.findall(tag):
            if not link.lower().startswith(b"data:"):
                return False
    return True


def looks_like_svg(data: bytes) -> bool:
    """Whether bytes are probably an SVG document (text with an ``<svg`` tag)."""
    head = data[:2000].lstrip(b"\xef\xbb\xbf \t\r\n")
    starts = (b"<?xml", b"<svg", b"<!--", b"<!DOCTYPE")
    return head.startswith(starts) and b"<svg" in data[:5000]


def svg_to_png(data: bytes) -> bytes | None:
    """An SVG as PNG bytes, or None if it can't be drawn (or resvg isn't there).

    Fonts aren't loaded and nothing outside the SVG is read. The renderer is
    native code, so even a panic inside it is caught and ends as None.
    """
    try:
        import resvg_py
    except ImportError:
        return None
    if not svg_is_self_contained(data):
        return None
    try:
        return bytes(
            resvg_py.svg_to_bytes(
                svg_string=data.decode("utf-8"),
                width=ICON_PIXELS * 2,
                skip_system_fonts=True,
            )
        )
    except (ValueError, UnicodeDecodeError):
        return None
    except BaseException as error:
        if isinstance(error, KeyboardInterrupt | SystemExit):
            raise
        return None


def to_png(data: bytes, target: Path) -> bool:
    """Write `data` (any image Pillow reads) to `target` as a small PNG."""
    try:
        from PIL import Image
    except ImportError:
        if data[:8] == b"\x89PNG\r\n\x1a\n":  # already what the list wants
            target.write_bytes(data)
            return True
        return False
    try:
        if looks_like_svg(data):
            drawn = svg_to_png(data)
            if drawn is None:
                return False
            data = drawn
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            converted = image.convert("RGBA")
        converted.thumbnail((ICON_PIXELS, ICON_PIXELS))
        converted.save(target, "PNG")
    except (OSError, ValueError, Image.DecompressionBombError):
        return False
    return True


def _key(ref: str) -> str:
    return hashlib.sha1(ref.encode("utf-8")).hexdigest()


def resolve_icon(
    root: Path, refs: list[IconRef], cache: Path | None
) -> tuple[Path | None, list[str]]:
    """The first usable icon as a PNG file, and the online icons still to fetch.

    Converted icons go in `cache`. Without one (no cache to write to) nothing
    is converted and None comes back.
    """
    pending: list[str] = []
    if cache is None:
        return None, pending
    for ref in refs:
        target = cache / f"{_key(ref.href)}.png"
        if target.exists():
            return target, pending
        if ref.href.startswith("data:"):
            data = decode_data_url(ref.href)
        elif ref.href.startswith(("http://", "https://")):
            raw = cache / f"{_key(ref.href)}.raw"
            data = raw.read_bytes() if raw.exists() else None
            if data is None and not (cache / f"{_key(ref.href)}.failed").exists():
                pending.append(ref.href)
        else:
            data = _read_local(root, ref.href)
        if data is None:
            continue
        cache.mkdir(parents=True, exist_ok=True)
        if to_png(data, target):
            return target, pending
    return None, pending


def fetch_remote(
    url: str, cache: Path, timeout: float = 5.0, opener: Opener = urlopen
) -> bool:
    """Download an online icon into the cache, once; True if it was fetched.

    A failure leaves a marker, so a missing or dead link isn't tried on every
    redraw of the list. Blocking: run it off the UI thread.
    """
    cache.mkdir(parents=True, exist_ok=True)
    key = _key(url)
    try:
        request = Request(url, headers={"User-Agent": "MyPyStub"})
        with opener(request, timeout=timeout) as response:
            data = response.read(MAX_ICON_BYTES + 1)
        if len(data) > MAX_ICON_BYTES:
            raise ValueError("icon too large")
        (cache / f"{key}.raw").write_bytes(data)
    except (OSError, ValueError):
        (cache / f"{key}.failed").write_bytes(b"")
        return False
    return True
