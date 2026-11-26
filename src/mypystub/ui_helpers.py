"""Plain helpers for the launcher's screens: tab sizes, backups, sharing."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import toga

import togax_jkingok
from togax_jkingok import share

# The app's own Python source, as shipped inside the bundle: this package's
# folder, and the widget package beside it (#323). Sharing it is a backstop to
# the About page's Source link, so anyone can read exactly what is running
# without trusting that link.
APP_SOURCE_DIR = Path(__file__).resolve().parent
SOURCE_DIRS = (APP_SOURCE_DIR, Path(togax_jkingok.__file__).resolve().parent)


def follow_tab_sizes(
    tabs: toga.OptionContainer, on_shown: Callable[[], Any] | None = None
) -> None:
    """Lay each tab out again whenever UIKit gives it a new size (iOS only).

    Toga's iOS OptionContainer lays a tab out when it's selected, but doesn't
    hear when UIKit sizes the tab's view afterwards. With iPadOS 26's floating
    tab bar a tab that wasn't on screen at launch is still 0 by 0 then, so it
    shows blank until something else (a rotation) lays it out. This does what
    Toga's window does for its own content: refresh on a change of size.

    `on_shown` is called when a tab first has a size, so that what was done on
    selecting it (such as scrolling the log to its end) can be done again
    now that it can be seen.
    """
    if sys.platform != "ios":
        return
    for container in tabs._impl.sub_containers:  # pyright: ignore[reportPrivateUsage]
        container.on_native_layout = _tab_resized(on_shown)


def _tab_resized(on_shown: Callable[[], Any] | None) -> Callable[[Any], None]:
    """A tab container's on_native_layout: refresh its content on a new size."""
    last: list[tuple[float, float]] = []

    def resized(container: Any) -> None:
        size = (float(container.width), float(container.height))
        if container.content is None or last == [size]:
            return
        shown = size[0] > 0 and size[1] > 0 and not (last and min(last[0]) > 0)
        last[:] = [size]
        container.content.interface.refresh()
        if shown and on_shown is not None:
            on_shown()

    return resized


def create_source_zip(app: toga.App) -> Path:
    """Zip the app's own Python source (its packages) for sharing or review.

    Everything in the package folders as shipped is included, in sorted order so
    the listing is stable, apart from ``__pycache__``. The file is named with
    the app's version, and written to the cache directory for a transient share.
    """
    name = f"{app.formal_name.lower().replace(' ', '_')}-{app.version}-source.zip"
    app.paths.cache.mkdir(parents=True, exist_ok=True)
    dest = app.paths.cache / name
    with ZipFile(dest, "w", ZIP_DEFLATED) as archive:
        for source in SOURCE_DIRS:
            for item in sorted(source.rglob("*")):
                relative = item.relative_to(source)
                if item.is_file() and "__pycache__" not in relative.parts:
                    archive.write(item, Path(source.name) / relative)
    return dest


# Where share sheets point, and how they're shown: now togax_jkingok.share's
share_anchor_rect = share.anchor_rect
configure_share_presentation = share.present_as_form_sheet


def open_share_sheet(w: toga.Widget, file_path: Path) -> bool:
    """
    Offers a file to the user's choice of app (togax_jkingok.share).

    The share sheet on iOS and Android (#217), the share menu on macOS, and
    the file manager on other desktops. On Android the file goes out through
    the app's own documents provider (:mod:`android_share`).

    :param w: The widget the share starts from; its window shows the sheet.
    :param file_path: The file to share.
    :returns: False if nothing could be shown.
    """
    android_uri = None
    if sys.platform == "android":
        from java import jclass  # pyright: ignore[reportMissingImports]

        from . import android_share

        def android_uri(path: Path) -> object:
            return android_share.content_uri(jclass, path)

    window = w.window or (w.app.main_window if w.app else None)
    return share.share_file(file_path, window, android_uri=android_uri)
