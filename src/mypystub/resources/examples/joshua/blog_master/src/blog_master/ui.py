import asyncio
import datetime as dt
import re
import shutil
from pathlib import Path

import toga
import yaml
from markdown import markdown as md

from . import settings as s
from . import widgets as ws


class Prototype:
    def __init__(self, host_app, on_done):
        self.app = host_app
        self.on_done_callback = on_done  # This is your ticket back to safety
        self.title = "Blog Master"  # host_app.formal_name
        self.app.settings = s.Settings(host_app.paths)
        self.data_path = self.app.paths.data
        self.this_path = Path(__file__).resolve().parent
        self.icon_path = self.this_path / "resources" / "icons"
        self.template_path = self.this_path / "resources" / "templates"
        self.fields = [
            ["layout", "text", "post"],
            ["title", "text", ""],
            ["date", "datetime", dt.datetime.now()],
            ["permalink", "text"],
            ["published", "bool", True],
            ["categories", "list"],
            ["tags", "list"],
            ["pin", "bool", False],
            # ["image", "image"]
        ]
        self.values = {f[0]: f[2] if len(f) > 2 else None for f in self.fields}
        self.values["image"] = None
        self.attachments = {}

    async def error(self, text):
        await self.app.main_window.dialog(toga.ErrorDialog("Error", text))

    async def info(self, text):
        await self.app.main_window.dialog(toga.InfoDialog("Info", text))

    async def todo(self, name):
        await self.app.main_window.dialog(toga.InfoDialog("TODO", name))

    def reset_pressed(self, button):
        # Reset model
        self.values = {f[0]: f[2] if len(f) > 2 else None for f in self.fields}
        self.values["image"] = None
        self.attachments = {}
        # Reset view
        for f in self.fields:
            ws.reset_form_field(*f)
        self.app.widgets["image"].reset()
        self.app.widgets["markdown"].value = ""

    def save_pressed(self, button):
        print(f"Saving {self.values}")
        if (
            self.values["title"]
            and self.values["image"]
            and self.app.widgets["markdown"]
        ):
            # Clean up
            def make_filename_safe(title: str, max_length: int = 50) -> str:
                """
                Converts an arbitrary string title into a safe lowercase filename.
                Removes special characters, replaces spaces with hyphens, and limits length.
                """
                # 1. Convert to lowercase
                safe_string = title.lower().strip()

                # 2. Replace spaces and underscores with a single hyphen
                safe_string = re.sub(re.compile(r"[\s_]+"), "-", safe_string)

                # 3. Strip out any character that isn't alphanumeric or a hyphen
                # We allow a-z, 0-9, and - specifically
                safe_string = re.sub(re.compile(r"[^a-z0-9\-]"), "", safe_string)

                # 4. Collapse any accidental consecutive hyphens (e.g., "a--b" -> "a-b")
                safe_string = re.sub(re.compile(r"-{2,}"), "-", safe_string)

                # 5. Clamp the string length to your maximum limit
                safe_string = safe_string[:max_length]

                # 6. Clean up any trailing or leading hyphens left over from truncating
                safe_string = safe_string.strip("-")

                return safe_string if safe_string else ""

            blog_dir = self.app.paths.data / "blog"
            entry_name = f"{self.values['date'].date()}-{make_filename_safe(self.values['title'])}"  # pyright: ignore[reportOptionalMemberAccess]
            file_path = f"_posts/{entry_name}.md"
            image_path_out = f"assets/img/posts/{entry_name}.png"
            front_matter = {}
            front_matter["layout"] = self.values["layout"]
            front_matter["date"] = (
                self.values["date"].astimezone().strftime("%Y-%m-%d %H:%M:%S %z")  # pyright: ignore[reportOptionalMemberAccess]
            )
            front_matter["title"] = self.values["title"]

            if v := self.values["categories"]:
                front_matter["categories"] = v
            if v := self.values["tags"]:
                front_matter["tags"] = v
            if v := self.values["permalink"]:
                front_matter["permalink"] = v
            if not self.values["published"]:
                front_matter["published"] = False
            if self.values["pin"]:
                front_matter["pin"] = True
            if self.values["image"]:
                front_matter["image"] = image_path_out

            Path(blog_dir / "_posts").mkdir(parents=True, exist_ok=True)
            image_dir = blog_dir / "assets/img/posts"
            image_dir.mkdir(parents=True, exist_ok=True)

            if self.values["image"]:
                shutil.move(self.values["image"], blog_dir / front_matter["image"])

            markdown = self.app.widgets["markdown"].value.replace(
                "Attachments/", f"assets/img/posts/{entry_name}/"
            )
            if self.attachments:
                attachment_dir = image_dir / entry_name
                attachment_dir.mkdir(parents=True, exist_ok=True)
                for k, v in self.attachments.items():
                    (attachment_dir / k.replace("Attachments/", "")).write_bytes(v)
            front_matter_md = yaml.dump(front_matter, sort_keys=False)
            Path(blog_dir / file_path).write_text(f"""---
{front_matter_md}---
{markdown}""")
            asyncio.create_task(self.info(f"Saved {entry_name}"))
        else:
            asyncio.create_task(
                self.error("A title, hero image and post content are all required.")
            )

    def paste_markdown(self, widget=None):
        # from typing import TypedDict
        import ctypes
        import io
        import zipfile

        from rubicon.objc import ObjCClass  # pyright: ignore[reportMissingImports]

        # class NotesPayload(TypedDict):
        #    markdown_content: str
        #    attachments: list[Path]
        markdown_content = ""
        self.attachments = {}

        UIPasteboard = ObjCClass("UIPasteboard")
        pb = UIPasteboard.generalPasteboard

        if pb.hasStrings:
            markdown_content = str(pb.string)
        else:
            uti = pb.pasteboardTypes[0]

            # 3. Pull the item as raw NSData
            ns_data = pb.dataForPasteboardType(uti)
            if ns_data is None:
                print(f"[-] Failed to retrieve NSData for type: {uti}")
                return False

            # 4. Extract pointer and length from the Objective-C NSData object
            data_bytes_ptr = ns_data.bytes
            data_length = ns_data.length

            if data_length == 0:
                print(f"[!] Target data length is 0 bytes for type: {uti}")
                return False

            print(
                f"[+] Found {data_length} bytes of raw data. Extracting from pointer..."
            )

            # 5. Use ctypes to copy the memory block into Python's memory space
            raw_zip_bytes = ctypes.string_at(data_bytes_ptr, data_length)

            if not zipfile.is_zipfile(io.BytesIO(raw_zip_bytes)):
                print("[-] Clipboard data is not a valid zip archive.")
                return False

            # attachment_paths: list[Path] = []

            # Wrap bytes in an in-memory stream container
            with zipfile.ZipFile(io.BytesIO(raw_zip_bytes)) as archive:
                # Extract everything into your local app's cache or document workspace
                # archive.extractall(path=extract_to_dir)

                # Walk through the extracted files to parse the specific folder layout
                for file_info in archive.infolist():
                    # Skip directories themselves
                    if file_info.is_dir():
                        continue

                    # 1. Identify and read the root Markdown file
                    if file_info.filename.lower().endswith(".md"):
                        try:
                            markdown_content += archive.read(file_info.filename).decode(
                                "utf-8"
                            )
                        except OSError as e:
                            print(f"[-] Failed to read markdown asset: {e}")

                    # 2. Identify and index components within the Attachments path
                    elif file_info.filename.find("/Attachments/") >= 0:
                        # markdown_content += f" and {file_info.filename}"
                        self.attachments[
                            "/".join(file_info.filename.split("/")[1:])
                        ] = archive.read(file_info.filename)

        self.app.widgets["markdown"].value = markdown_content

    def set_image(self, img):
        self.values["image"] = img

    def get_content(self):
        return toga.OptionContainer(
            content=[
                (
                    "Metadata",
                    toga.Column(
                        children=[
                            toga.Divider(),
                            *[
                                ws.create_form_field(
                                    *field,
                                    callback=lambda w, k=field[0], t=field[1]: (
                                        self.values.update(
                                            {
                                                k: w.value.split(" ")
                                                if t == "list"
                                                else w.value
                                            }
                                        )
                                    ),
                                )
                                for field in self.fields
                            ],
                            toga.Divider(),
                            toga.Box(flex=1),
                            toga.Row(
                                children=[
                                    toga.Button(
                                        "Reset", on_press=self.reset_pressed, flex=1
                                    ),
                                    toga.Button(
                                        "Save",
                                        on_press=lambda w: self.save_pressed(w),
                                        flex=1,
                                    ),
                                ]
                            ),
                        ]
                    ),
                ),
                (
                    "Image",
                    ws.ImagePanel(
                        direction="column",
                        callback=lambda w: self.set_image(w.value),
                        id="image",
                    ),
                ),
                (
                    "Content",
                    toga.Column(
                        children=[
                            toga.Button("Paste", on_press=self.paste_markdown),
                            toga.MultilineTextInput(
                                id="markdown",
                                on_change=lambda w: setattr(
                                    self.app.widgets["preview"], "value", w.value
                                ),
                                flex=1,
                            ),
                            toga.Divider(),
                            ws.MarkdownView(id="preview", flex=1),
                        ]
                    ),
                ),
                (
                    "Setup",
                    toga.Column(
                        children=[
                            toga.Button(
                                "Exit",
                                visibility="visible"
                                if hasattr(self.app.main_window, "content_stack")
                                and len(self.app.main_window.content_stack) > 0
                                else "hidden",
                                on_press=self.on_done_callback,
                            )
                        ]
                    ),
                    self.icon_path / "settings-sliders.png",
                ),
                (
                    "Help",
                    toga.Row(
                        children=[
                            toga.WebView(
                                content=f"""
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; line-height: 1.6; padding: 20px; color: #333; }}
                code {{ background-color: #f6f8fa; padding: 2px 4px; border-radius: 3px; font-family: monospace; }}
                pre {{ background-color: #f6f8fa; padding: 16px; overflow: auto; border-radius: 6px; }}
                img {{ max-width: 100%; height: auto; }}
            </style>
        </head>
        <body>
                     {md(f.read_text() if (f := (self.template_path / "help.md")).exists() else "")}
        </body>
        </html>
""",
                                flex=1,
                            )
                        ]
                    ),
                    self.icon_path / "interrogation.png",
                ),
            ],
        )
