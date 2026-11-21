# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "rubicon-objc; sys_platform == 'darwin'",
# ]
# ///
"""Save the text on the pasteboard as an HTML file in the current folder.

Asks for the file name with input(). If the pasteboard can't be read (for
example on a desktop Python), it asks you to paste the text instead, ending
with an empty line.
"""

import os
import sys
from pathlib import Path


def read_pasteboard():
    """Text on the iOS pasteboard via rubicon-objc, or None if unavailable."""
    if sys.platform != "ios":
        return None
    try:
        # toga_iOS doesn't provide UIPasteboard, so it's looked up here
        from rubicon.objc import ObjCClass  # pyright: ignore[reportMissingImports]

        text = ObjCClass("UIPasteboard").generalPasteboard.string
        return str(text) if text is not None else None
    except Exception:  # noqa: BLE001
        return None


def read_pasted_text():
    print("Paste your text, then press Enter on an empty line:")
    lines = []
    while True:
        line = input()
        if line == "":
            break
        lines.append(line)
    return "\n".join(lines)


def html_name(name):
    name = name.strip().replace("/", "_").replace("\\", "_")
    if not name:
        raise SystemExit("No file name given.")
    if not name.lower().endswith((".html", ".htm")):
        name += ".html"
    return name


def main():
    text = read_pasteboard()
    if text is None:
        text = read_pasted_text()
    if not text.strip():
        raise SystemExit("The pasteboard has no text.")

    path = Path(os.getcwd()) / html_name(input("File name: "))
    if (
        path.exists()
        and input(f"{path.name} exists. Overwrite? (y/N): ").strip().lower() != "y"
    ):
        raise SystemExit("Not saved.")

    path.write_text(text, encoding="utf-8")
    print(f"Saved {path}")


if __name__ == "__main__":
    main()
