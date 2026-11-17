"""Report what's on the pasteboard (iOS) or clipboard (Android), and what could use it.

Copy something, run this, and read the Verdict at the end. iOS may ask whether
to allow pasting, and Android 12+ shows a "pasted from your clipboard" note:
that is part of what's being tested. The report is also saved as
paste_report.txt, and each type's raw bytes go in paste_dump/, both in
Documents, so they can be shared.
"""

import ctypes
import platform
import re
import shutil
import sys
import tarfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Any

# Apple's base-32 alphabet for dynamic type identifiers
DYN_ALPHABET = "abcdefghkmnpqrstuvwxyz0123456789"

# Registered first by the Files app, but these are private bookmarks (binary
# plists), not the file: reading one gets the wrong bytes
FILES_APP_TYPES = "com.apple.DocumentManager.FINode."
BOOKMARK_TYPES = (FILES_APP_TYPES, "com.apple.uikit.useractivity")
FOLDER_TYPE = "public.folder"

LOAD_TIMEOUT = 30.0  # seconds to wait for one type, such as an iCloud download
DUMP_LIMIT = 1024 * 1024  # types bigger than this aren't dumped

lines: list[str] = []


def say(text: str = "") -> None:
    """Print a line and keep it for the saved report."""
    print(text)
    lines.append(text)


def decode_dyn_uti(uti: str) -> str:
    """Show what a dynamic type (``dyn.a...``) stands for, beside the type itself."""
    if not uti.lower().startswith("dyn.a"):
        return uti
    value = bits = 0
    decoded = bytearray()
    for char in uti[5:].lower():
        if char not in DYN_ALPHABET:
            return uti
        value = (value << 5) | DYN_ALPHABET.index(char)
        bits += 5
        if bits >= 8:
            bits -= 8
            decoded.append((value >> bits) & 0xFF)
            value &= (1 << bits) - 1
    try:
        return f"{uti} ({decoded.decode('utf-8')})"
    except UnicodeDecodeError:
        return uti


def file_type(types: list[str], has_text: bool) -> str | None:
    """The type Paste reads a file from: Files app copies always, text never."""
    content = [uti for uti in types if not uti.startswith(BOOKMARK_TYPES)]
    from_files = any(uti.startswith(FILES_APP_TYPES) for uti in types)
    if FOLDER_TYPE in types or not content or (has_text and not from_files):
        return None
    return content[0]


def sniff(path: Path) -> str:
    """What a file's bytes look like, whatever its name says."""
    if path.is_dir():
        return "a folder"
    with path.open("rb") as file:
        head = file.read(512)
    if not head:
        return "empty"
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            return f"zip, {len(archive.namelist())} entries"
    if tarfile.is_tarfile(path):
        with tarfile.open(path) as archive:
            return f"tar, {len(archive.getnames())} entries"
    if head.startswith(b"bplist"):
        return "binary plist (a bookmark, not the file?)"
    try:
        return f"text: {head[:40].decode('utf-8')!r}"
    except UnicodeDecodeError:
        return f"binary, starts {head[:8].hex()}"


def nserror(error: Any) -> str:
    """An NSError as its domain, code and message."""
    return f"{error.domain} {error.code}: {error.localizedDescription}"


def load_file(provider: Any, uti: str) -> dict[str, Any]:
    """Ask an item provider for `uti` as a file, as Paste does.

    The file only lasts until the callback returns, and the callback runs on a
    background thread, so it's measured there.
    """
    from rubicon.objc import (  # pyright: ignore[reportMissingImports]
        Block,
        ObjCInstance,
        objc_id,
    )

    done = threading.Event()
    result: dict[str, Any] = {}

    def finished(url: Any, error: Any) -> None:
        try:
            if error:
                result["error"] = nserror(ObjCInstance(error))
            if url:
                path = Path(str(ObjCInstance(url).path))
                result["name"] = path.name
                result["size"] = path.stat().st_size
                result["looks like"] = sniff(path)
        except Exception as problem:  # noqa: BLE001
            result["exception"] = repr(problem)
        finally:
            done.set()

    started = time.monotonic()
    block = Block(finished, None, objc_id, objc_id)
    provider.loadFileRepresentationForTypeIdentifier(uti, completionHandler=block)
    if not done.wait(LOAD_TIMEOUT):
        result["error"] = f"no answer after {LOAD_TIMEOUT:.0f} seconds"
    result["seconds"] = round(time.monotonic() - started, 2)
    return result


def report_counts(pasteboard: Any) -> tuple[bool, bool, list[str]]:
    """Report what iOS says is there, which needs no permission to ask."""
    has_urls = bool(pasteboard.hasURLs)
    has_strings = bool(pasteboard.hasStrings)
    types = [str(uti) for uti in pasteboard.pasteboardTypes]
    say("== Pasteboard ==")
    say(f"changeCount {pasteboard.changeCount}, items {pasteboard.numberOfItems}")
    say(f"hasURLs {has_urls}, hasStrings {has_strings}")
    say(f"hasImages {bool(pasteboard.hasImages)}, hasColors {pasteboard.hasColors}")
    for uti in types:
        say(f"  type {decode_dyn_uti(uti)}")
    return has_urls, has_strings, types


def report_url(pasteboard: Any) -> bool:
    """Report a copied URL; True if it's a file Paste could read directly."""
    say()
    say("== URL ==")
    url = pasteboard.URL
    if url is None:
        say("hasURLs is true, but reading the URL gave nothing (Don't Allow Paste?)")
        return False
    say(f"{url.absoluteString}, file URL: {bool(url.isFileURL)}")
    if not url.isFileURL:
        return False
    path = Path(str(url.path))
    say(f"security scope granted: {bool(url.startAccessingSecurityScopedResource())}")
    say(f"exists: {path.exists()}")
    if path.is_file():
        say(f"size {path.stat().st_size}, looks like {sniff(path)}")
    return path.is_file()


def report_text(pasteboard: Any) -> bool:
    """Report copied text; True if there is some."""
    say()
    say("== Text ==")
    text = pasteboard.string
    if text is None or not str(text):
        say("hasStrings is true, but reading it gave nothing (Don't Allow Paste?)")
        return False
    say(f"{len(str(text))} characters, starting {str(text)[:60]!r}")
    return True


def report_providers(pasteboard: Any, has_text: bool) -> dict[str, Any]:
    """Try each item provider's types as a file; returns what Paste would use."""
    say()
    say("== Item providers ==")
    providers = list(pasteboard.itemProviders)
    say(f"{len(providers)} provider(s)")
    found: dict[str, Any] = {}
    for number, provider in enumerate(providers, 1):
        types = [str(uti) for uti in provider.registeredTypeIdentifiers]
        say(f"Item {number}: suggested name {provider.suggestedName}")
        chosen = file_type(types, has_text) if number == 1 else None
        for uti in types:
            result = load_file(provider, uti)
            say(f"  {decode_dyn_uti(uti)}")
            say(f"    {'used by Paste' if uti == chosen else 'not used'}: {result}")
            if uti == chosen:
                found["file"] = result
        if number == 1 and FOLDER_TYPE in types:
            found["folder"] = True
    return found


def dump_types(pasteboard: Any, types: list[str], folder: Path) -> None:
    """Save each type's raw bytes, to compare against the original."""
    say()
    say(f"== Raw bytes, in {folder.name}/ ==")
    folder.mkdir(exist_ok=True)
    for uti in types:
        data = pasteboard.dataForPasteboardType(uti)
        if data is None:
            say(f"  {uti}: no data")
        elif data.length > DUMP_LIMIT:
            say(f"  {uti}: {data.length} bytes, too big to dump")
        else:
            name = re.sub(r"[^A-Za-z0-9._-]", "_", uti)
            (folder / name).write_bytes(ctypes.string_at(data.bytes, data.length))
            say(f"  {uti}: {data.length} bytes, saved as {name}")


def report_destination(documents: Path) -> bool:
    """Report whether Documents can be written to; True if so."""
    say()
    say("== Documents ==")
    probe = documents / ".paste_diagnostics_probe"
    try:
        probe.write_text("probe")
        probe.unlink()
    except OSError as error:
        say(f"Can't write here: {error}")
        return False
    say(f"Writable, {shutil.disk_usage(documents).free // 1024**2} MB free")
    return True


def verdict(found: dict[str, Any], items: int, writable: bool) -> str:
    """What Paste would do with this, and what to try if it can't."""
    if not writable:
        return "Paste can't save anything: Documents isn't writable."
    if found["url"]:
        return "Paste would import the copied file URL."
    if found.get("folder"):
        return "Paste would say a folder can't be pasted. Compress it in Files first."
    if found.get("file"):
        file = found["file"]
        if "size" in file:
            return f"Paste would import {file['name']}."
        return f"Paste would fail to read the file: {file}"
    if found["text"]:
        return "Paste would treat the text as Python, and ask for a file name."
    if items:
        return (
            "Paste would say there's nothing to paste: something is copied, but it "
            "couldn't be read. If you chose Don't Allow Paste, try again and allow "
            "it, or check Paste from Other Apps in this app's page in Settings. "
            "Otherwise look for errors under Item providers."
        )
    return "The pasteboard is empty. Copy something, then run this again."


def ios_main() -> None:
    """Write the report from the iOS pasteboard."""
    from rubicon.objc import ObjCClass  # pyright: ignore[reportMissingImports]

    documents = Path.home() / "Documents"
    say("== Device ==")
    say(f"Python {platform.python_version()}, {platform.ios_ver()}")
    # toga_iOS doesn't declare UIPasteboard, so it's looked up here
    pasteboard = ObjCClass("UIPasteboard").generalPasteboard
    has_urls, has_strings, types = report_counts(pasteboard)
    items = int(pasteboard.numberOfItems)

    # Reading contents, not just counts, is what makes iOS ask to allow pasting
    found: dict[str, Any] = {"url": False, "text": False}
    if has_urls:
        found["url"] = report_url(pasteboard)
    if has_strings:
        found["text"] = report_text(pasteboard)
    if items:
        found |= report_providers(pasteboard, has_strings)
        dump_types(pasteboard, types, documents / "paste_dump")
    writable = report_destination(documents)

    say()
    say("== Verdict ==")
    say(verdict(found, items, writable))
    if writable:
        (documents / "paste_report.txt").write_text("\n".join(lines) + "\n")


# -- Android --------------------------------------------------------------------
# The clipboard is ClipboardManager. Its ClipData holds items, each text, HTML or a
# content:// URI. Android 12+ shows a note when a script reads the content, and
# 10+ only answers the app that has focus. A URI is read through ContentResolver,
# which the clipboard grants to the app that fetched the clip.

OPENABLE_NAME, OPENABLE_SIZE = "_display_name", "_size"
SENSITIVE = "android.content.extra.IS_SENSITIVE"  # API 33+


def android_activity() -> Any:
    """The running activity: Briefcase's MainActivity keeps itself in a static."""
    from java import jclass  # pyright: ignore[reportMissingImports]

    return jclass("org.beeware.android.MainActivity").singletonThis


def android_device(activity: Any) -> None:
    """Report the device, the focus the clipboard needs, and how we were started."""
    from java import jclass  # pyright: ignore[reportMissingImports]

    build, version = jclass("android.os.Build"), jclass("android.os.Build$VERSION")
    say("== Device ==")
    say(f"Python {platform.python_version()}, Android {version.RELEASE}")
    say(f"API {version.SDK_INT}, {build.MANUFACTURER} {build.MODEL}")
    say(f"window focus: {bool(activity.hasWindowFocus())} (10+ needs it to read)")
    launch = activity.getIntent()
    say(f"started with {launch.getAction()}, type {launch.getType()}")


def android_clip_counts(activity: Any) -> tuple[Any, bool]:
    """Report what the clipboard says it holds, which shows no note and needs no focus."""
    from java import jclass  # pyright: ignore[reportMissingImports]

    manager = activity.getSystemService(
        jclass("android.content.Context").CLIPBOARD_SERVICE
    )
    has_clip = bool(manager.hasPrimaryClip())
    say()
    say("== Clipboard ==")
    say(f"hasPrimaryClip {has_clip}")
    description = manager.getPrimaryClipDescription()
    if description is None:
        return manager, False
    say(f"label {description.getLabel()}, {description.getMimeTypeCount()} type(s)")
    for number in range(description.getMimeTypeCount()):
        say(f"  type {description.getMimeType(number)}")
    try:
        age = time.time() - description.getTimestamp() / 1000
        say(f"copied {age:.0f} seconds ago")
        extras = description.getExtras()
        if extras is not None and extras.getBoolean(SENSITIVE):
            say("marked sensitive: the copying app asks for it to be hidden")
    except Exception as problem:  # noqa: BLE001  (older than API 26 or 33)
        say(f"no timestamp or sensitive flag: {problem!r}")
    return manager, has_clip


def read_uri(activity: Any, uri: Any, folder: Path) -> dict[str, Any]:
    """Open a content URI as Paste would: type, name, size, then save the bytes."""
    from java import jarray, jbyte  # pyright: ignore[reportMissingImports]

    resolver = activity.getContentResolver()
    result: dict[str, Any] = {}
    started = time.monotonic()
    try:
        result["type"] = resolver.getType(uri)
        cursor = resolver.query(uri, None, None, None, None)
        if cursor is not None:
            try:
                if cursor.moveToFirst():
                    for column, key in (
                        (OPENABLE_NAME, "name"),
                        (OPENABLE_SIZE, "size"),
                    ):
                        index = cursor.getColumnIndex(column)
                        if index >= 0:
                            result[key] = str(cursor.getString(index))
            finally:
                cursor.close()
        stream = resolver.openInputStream(uri)
        data, buffer = b"", jarray(jbyte)(65536)
        while len(data) <= DUMP_LIMIT:
            count = stream.read(buffer)
            if count < 0:
                break
            data += bytes(memoryview(buffer))[:count]
        stream.close()
        name = re.sub(r"[^A-Za-z0-9._-]", "_", result.get("name") or "item")
        folder.mkdir(exist_ok=True)
        (folder / name).write_bytes(data)
        result["saved as"] = name
        result["read"] = len(data)
        result["looks like"] = sniff(folder / name)
    except Exception as problem:  # noqa: BLE001
        result["exception"] = repr(problem)
    result["seconds"] = round(time.monotonic() - started, 2)
    return result


def android_items(activity: Any, manager: Any, folder: Path) -> dict[str, Any]:
    """Read the clip: this is what shows the Android 12 note. Try each URI."""
    say()
    say(f"== Items, raw bytes in {folder.name}/ ==")
    found: dict[str, Any] = {"text": False, "files": []}
    clip = manager.getPrimaryClip()
    if clip is None:
        say("hasPrimaryClip is true, but reading the clip gave nothing (no focus?)")
        return found
    for number in range(clip.getItemCount()):
        item = clip.getItemAt(number)
        say(f"Item {number + 1}:")
        text, html, uri = item.getText(), item.getHtmlText(), item.getUri()
        if text is not None:
            say(f"  text: {len(str(text))} characters, starting {str(text)[:60]!r}")
            found["text"] = True
        if html is not None:
            say(f"  html: {len(str(html))} characters")
        if uri is not None:
            say(f"  uri: {uri}")
            result = read_uri(activity, uri, folder)
            say(f"    {result}")
            found["files"].append(result)
    return found


def android_verdict(found: dict[str, Any], has_clip: bool, writable: bool) -> str:
    """What Paste would do with this clip, and what to try if it can't."""
    if not writable:
        return "Paste can't save anything: the documents folder isn't writable."
    files = found.get("files", [])
    for file in files:
        if "exception" in file or file.get("read", 0) == 0:
            return f"Paste would fail to read a copied file: {file}"
    if files:
        names = ", ".join(file.get("name", "a file") for file in files)
        return f"Paste would import {names}."
    if found.get("text"):
        return "Paste would treat the text as Python, and ask for a file name."
    if has_clip:
        return (
            "Something is copied, but nothing could be read. Android only gives the "
            "clipboard to the app with focus, and a copied value may be hidden as "
            "sensitive. Look for errors under Items."
        )
    return "The clipboard is empty. Copy something, then run this again."


def android_main() -> None:
    """Write the report from the Android clipboard."""
    activity = android_activity()
    documents = Path(str(activity.getFilesDir().getAbsolutePath()))
    android_device(activity)
    manager, has_clip = android_clip_counts(activity)
    found = (
        android_items(activity, manager, documents / "paste_dump") if has_clip else {}
    )
    writable = report_destination(documents)
    say()
    say("== Verdict ==")
    say(android_verdict(found, has_clip, writable))
    if writable:
        (documents / "paste_report.txt").write_text("\n".join(lines) + "\n")


def main() -> None:
    """Write the report for this platform."""
    if sys.platform == "ios":
        ios_main()
    elif sys.platform == "android":
        android_main()
    else:
        print(
            "This reads the clipboard on iPhone, iPad or Android, so it only runs there."
        )


if __name__ == "__main__":
    main()
