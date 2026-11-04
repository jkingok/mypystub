"""Paste: add a copied file, archive or script to the folder being browsed."""

from __future__ import annotations

import asyncio
import sys
import tarfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import BadZipFile

import toga

from . import info_pages, paste_import, prompts
from .ui_base import PrototypeBase


class PasteMixin(PrototypeBase):
    """Paste a copied file, archive or script into the folder being browsed."""

    def __init__(self, host_app: toga.App, on_done: Callable[[Any], None]) -> None:
        super().__init__(host_app, on_done)
        self.paste_button = toga.Button("Paste", on_press=self.handle_paste)
        self.add_button_icon(self.paste_button, "paste.png")
        if sys.platform != "ios":
            self.paste_button.style.display = "none"  # no pasteboard to read
        # What a shown preview would import, until Cancel or Import
        self._pending_import: tuple[str, str, Path] | None = None
        self.import_button: toga.Button | None = None

    def add_button_icon(
        self, button: toga.Button, icon_file: str, size: int = 20
    ) -> None:
        """On iOS, draw a bundled icon beside a button's text, tinted like it.

        Toga won't give a button both text and an icon, so the image is set
        natively (the same call toga-iOS makes), as a template so it follows
        the button's colour and dark mode. Nothing happens if the icon file
        hasn't been added, or off iOS.
        """
        path = self.icon_path / icon_file
        if sys.platform != "ios" or not path.exists():
            return
        from toga_iOS.libs import UIControlStateNormal

        image = (
            toga.Icon(path)
            ._impl._as_size(size)
            .imageWithRenderingMode(2)  # UIImageRenderingModeAlwaysTemplate
        )
        button._impl.native.setImage(image, forState=UIControlStateNormal)
        # Toga measured the button from its text alone; measure it again now
        # that the image is there, or the label can be squeezed ("P...te")
        button.refresh()

    async def ask_text(self, title: str, label: str, initial: str) -> str | None:
        """Ask for a line of text; None if cancelled."""
        texts = await self.ask_fields(title, "", [prompts.Field(label, initial)])
        return None if texts is None else texts[0]

    async def handle_paste(
        self, widget: toga.Widget | None = None, **kwargs: Any
    ) -> None:
        """Preview what's on the pasteboard, then Cancel or Import it (#36).

        The preview is the Info of the thing being added: a pasted script's
        source, a file's or zipapp's Info, or an archive's contents. Import
        then copies the file, extracts the archive into a new folder, or saves
        the text, asking for a file name only when one is needed (pasted text,
        or a name clash).
        """
        from . import bridge

        if self.category != "Documents":
            await self.info(
                "Open Documents (or a folder in it) first: the bundled examples "
                "can't be changed.",
                "Paste",
            )
            return
        try:
            content = await bridge.read_pasteboard(Path(self.app.paths.cache) / "paste")
        except (OSError, ValueError) as error:
            await self.error(f"Couldn't paste: {error}", "Paste")
            return
        if content is None:
            await self.info(
                "Copy a script as text, or a file in the Files app, then paste. "
                "If iOS asks, choose Allow Paste.",
                "Nothing to paste",
            )
            return
        kind, value = content
        folder = self.get_current_dir()
        screen_title, body, can_import = self.import_preview(kind, value)
        self._pending_import = (kind, value, folder)
        self.show_import_preview(screen_title, body, can_import)

    def import_preview(self, kind: str, value: str) -> tuple[str, str, bool]:
        """A paste's screen title, Info HTML, and whether it can be imported."""
        if kind != "file":
            body = info_pages.section("Pasted Python", info_pages.source_html(value))
            return "Paste", body, True
        path = Path(value)
        name = path.name
        if paste_import.is_archive(name):
            try:
                tops = paste_import.archive_top_level(path)
            except (OSError, tarfile.TarError, BadZipFile):
                body = (
                    f"<h1>{info_pages.escape(name)}</h1>\n"
                    "<p>This archive can't be read, so it can't be imported. It "
                    "may be damaged, or not really an archive.</p>"
                )
                return name, body, False
            listing = info_pages.bullet_list(tops) if tops else "<p>(empty)</p>"
            body = (
                info_pages.section("Archive contents", listing)
                + "<p>Import extracts these into a new folder here.</p>"
            )
            return name, body, True
        if path.suffix == ".py":
            return name, info_pages.script_info_html(path, path.stem), True
        if path.suffix == ".pyz":
            return name, info_pages.zipapp_info_html(path, path.stem), True
        body = (
            f"<h1>{info_pages.escape(name)}</h1>\n"
            f"<p>{info_pages.escape(name)} will be copied here as it is.</p>"
        )
        return name, body, True

    def show_import_preview(
        self, screen_title: str, body: str, can_import: bool = True
    ) -> None:
        """Show the import preview, with Cancel and Import in place of Back."""
        view = toga.WebView(flex=1, on_navigation_starting=self.open_external)
        self.load_page(view, body)
        self.import_button = toga.Button(
            "Import", on_press=self.confirm_import, enabled=can_import
        )
        top = toga.Row(
            children=[
                toga.Button("✕ Cancel", on_press=self.cancel_import),
                toga.Box(flex=1),
                self.import_button,
            ]
        )
        self.push_screen(screen_title, toga.Column(children=[top, view]))

    def cancel_import(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Discard the previewed item without importing it."""
        self._pending_import = None
        self.pop_screen()

    def confirm_import(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Import button: carry out the import for the previewed item."""
        asyncio.ensure_future(self._do_import())

    async def _do_import(self) -> None:
        """Perform the pending import, then return to the list."""
        pending = self._pending_import
        self._pending_import = None
        self.pop_screen()
        if pending is None:
            return
        kind, value, folder = pending
        try:
            if kind == "file":
                added = await self.paste_file(Path(value), folder)
            else:
                added = await self.paste_text(value, folder)
        except (OSError, ValueError, tarfile.TarError, BadZipFile) as error:
            await self.error(f"Couldn't paste: {error}", "Paste")
            return
        if added is not None:
            self.reload_menu(self.script_list)
            await self.info(f"Added {added.name}.", "Pasted")

    async def paste_file(self, source: Path, folder: Path) -> Path | None:
        """Copy a pasted file, or extract a pasted archive into a new folder."""
        if paste_import.is_archive(source.name):
            return paste_import.extract_archive(source, folder)
        overwrite = False
        if paste_import.would_overwrite(folder, source.name):
            overwrite = await self.ask(
                "Replace existing file?",
                f"{source.name} already exists. Replace it? Choose No to keep both.",
            )
        return paste_import.import_file(source, folder, overwrite)

    async def paste_text(self, text: str, folder: Path) -> Path | None:
        """Save pasted text, taken to be Python, under a name the user gives."""
        suggestion = paste_import.default_filename(datetime.now())
        while True:
            typed = await self.ask_text(
                "Paste", "File name for the pasted code", suggestion
            )
            if typed is None:
                return None
            name = paste_import.clean_filename(typed)
            if name is not None:
                break
            await self.info("Enter a file name.", "Paste")
        overwrite = False
        if paste_import.would_overwrite(folder, name):
            overwrite = await self.ask(
                "Replace existing file?",
                f"{name} already exists. Replace it? Choose No to keep both.",
            )
        return paste_import.import_text(text, name, folder, overwrite)
