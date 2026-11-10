"""Static web apps: a folder with an ``index.html``, or a single ``.html`` file.

The server is adapted from Toga's ``positron-static`` template (BeeWare,
BSD-3-Clause, ``toga_positron/static/templates/app.py.tmpl``): a threaded
``http.server`` on 127.0.0.1 with an OS-chosen port, serving a base directory
to a ``toga.WebView``. Only the base-path handling differs: a single file is
served from its own folder, and logging is quiet.
"""

from __future__ import annotations

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

from . import web_meta

HTML_SUFFIXES = (".html", ".htm")
INDEX = "index.html"


class HTTPHandler(SimpleHTTPRequestHandler):
    """Serve files from the server's ``base_path`` (as positron-static does)."""

    def translate_path(self, path: str) -> str:
        path = path.split("?", 1)[0].split("#", 1)[0]
        base: Path = self.server.base_path  # type: ignore[attr-defined]
        target = (base / path.lstrip("/")).resolve()
        if not target.is_relative_to(base.resolve()):
            return str(base)  # never serve outside the app's folder
        return str(target)

    def log_message(self, format: str, *args: Any) -> None:
        """Stay quiet: the Logs tab is for the user's prototypes."""


class LocalHTTPServer(ThreadingHTTPServer):
    """Listens on 127.0.0.1, on a port the OS chooses."""

    daemon_threads = True

    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path
        super().__init__(("127.0.0.1", 0), HTTPHandler)


class StaticServer:
    """Runs a :class:`LocalHTTPServer` on a thread until :meth:`stop`."""

    def __init__(self, base_path: Path, page: str = INDEX) -> None:
        self.page = page
        self._httpd = LocalHTTPServer(base_path)  # listening; serving starts below
        self._thread = Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        """Where the app's page is."""
        host, port = self._httpd.socket.getsockname()[:2]
        return f"http://{host}:{port}/{self.page}"

    def start(self) -> str:
        """Start serving; returns the URL of the page."""
        self._thread.start()
        return self.url

    def stop(self) -> None:
        """Stop serving and release the port."""
        if self._thread.is_alive():
            self._httpd.shutdown()
        self._httpd.server_close()


def is_web_page(path: Path) -> bool:
    """Whether `path` is a standalone HTML file."""
    return path.is_file() and path.suffix.lower() in HTML_SUFFIXES


def is_web_folder(path: Path) -> bool:
    """A folder with an index.html and no pyproject.toml (those are projects)."""
    return (
        path.is_dir()
        and (path / INDEX).is_file()
        and not (path / "pyproject.toml").exists()
    )


def page_details(root: Path, page: str) -> web_meta.PageMeta:
    """The metadata in the app's page (empty if it can't be read)."""
    try:
        text = (root / page).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return web_meta.PageMeta()
    return web_meta.parse_page(text)


def scan_web(item: Path, icon_cache: Path | None = None) -> dict[str, Any]:
    """The launcher row for a web app folder or a standalone page.

    The subtitle is the app's description (manifest, then page), else its title.
    `icon_cache` is where the app's icon, converted for the list, is kept. An
    online icon not fetched yet is listed under ``icon_pending``.
    """
    if item.is_dir():
        root, page, name = item, INDEX, item.name
    else:
        root, page, name = item.parent, item.name, item.stem
    meta = page_details(root, page)
    manifest = web_meta.load_manifest(root, meta)
    icon, pending = web_meta.resolve_icon(
        root, web_meta.icon_candidates(meta, manifest), icon_cache
    )
    return {
        "title": name,
        "subtitle": web_meta.display_description(meta, manifest)
        or web_meta.display_title(meta, manifest)
        or "Web app",
        "icon_path": icon,
        "icon_pending": pending,
        "kind": "web",
        "web_root": root,
        "web_page": page,
        "project_dir": item,
        "folder_root": item,
        "dependencies": [],
        "aliases": {},
    }
