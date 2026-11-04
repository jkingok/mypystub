"""Paste: add a copied file, archive or script to the folder being browsed."""

from __future__ import annotations

import sys
import tarfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import BadZipFile

import toga

from . import paste_import, prompts
from .ui_base import PrototypeBase


class PasteMixin(PrototypeBase):
    """Paste a copied file, archive or script into the folder being browsed."""

    def __init__(self, host_app: toga.App, on_done: Callable[[Any], None]) -> None:
        super().__init__(host_app, on_done)
        self.paste_button = toga.Button("Paste", on_press=self.handle_paste)
        self.add_button_icon(self.paste_button, "paste.png")
        if sys.platform != "ios":
            self.paste_button.style.display = "none"  # no pasteboard to read

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
        """Add what's on the pasteboard to the folder being browsed (#36).

        A copied file is preferred and kept as it is; an archive is offered for
        extraction. Copied text is taken to be Python, and a file name is
        asked for. Nothing is overwritten unless the user says so; otherwise
        an incrementing name is used.
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
        folder = self.get_current_dir()
        kind, value = content
        try:
            if kind == "file":
                added = await self.paste_file(Path(value), folder)
            else:
                added = await self.paste_text(value, folder)
        except (
            OSError,
            ValueError,
            tarfile.TarError,
            BadZipFile,
        ) as error:
            await self.error(f"Couldn't paste: {error}", "Paste")
            return
        if added is not None:
            self.reload_menu(self.script_list)
            await self.info(f"Added {added.name}.", "Pasted")

    async def paste_file(self, source: Path, folder: Path) -> Path | None:
        """Copy or extract a pasted file."""
        if paste_import.is_archive(source.name) and await self.ask(
            "Extract archive?",
            f"{source.name} is an archive. Extract it into a folder here? "
            "Choose No to keep it as it is.",
        ):
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
