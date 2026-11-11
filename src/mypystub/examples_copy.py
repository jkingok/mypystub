"""Keep the bundled examples where their scripts can see their own files.

On Android, Chaquopy keeps the examples' ``.py`` files inside the APK. The
launcher can't list them from disk, and a script can't find a data file beside
it with :mod:`pathlib`. So on Android the whole examples tree is copied into the
app's cache folder, which is private to the app. It is never the Documents
folder, which the Files app shares with the user.

Other platforms use the bundled folder as it is.
"""

import hashlib
import shutil
from importlib.resources.abc import Traversable
from pathlib import Path

# Hidden, so the launcher doesn't list it. Holds the hash of the copied tree.
STAMP_NAME = ".examples-hash"


def content_hash(source: Traversable) -> str:
    """A hash of every file's path and bytes under ``source``.

    The copy is rebuilt when this changes, so an update to an example is picked
    up without changing the app's version.
    """
    digest = hashlib.sha256()
    for path in sorted(_walk(source), key=lambda p: p[0]):
        name, data = path
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    return digest.hexdigest()


def _walk(source: Traversable, prefix: str = "") -> list[tuple[str, bytes]]:
    """Every file under ``source`` as ``(relative path, bytes)``."""
    found: list[tuple[str, bytes]] = []
    for child in source.iterdir():
        name = f"{prefix}{child.name}"
        if child.is_dir():
            found += _walk(child, f"{name}/")
        else:
            found.append((name, child.read_bytes()))
    return found


def copy_tree(source: Traversable, dest: Path) -> None:
    """Copy every file under ``source`` into ``dest``, keeping the folders."""
    dest.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        target = dest / child.name
        if child.is_dir():
            copy_tree(child, target)
        else:
            target.write_bytes(child.read_bytes())


def refresh_copy(source: Traversable, dest: Path) -> Path:
    """Make ``dest`` a copy of ``source``, rebuilding it only when it has changed.

    Returns ``dest``. A rebuild removes the old copy first, so a file removed from
    the source doesn't linger.
    """
    current = content_hash(source)
    stamp = dest / STAMP_NAME
    if stamp.exists() and stamp.read_text(encoding="utf-8") == current:
        return dest
    if dest.exists():
        shutil.rmtree(dest)
    copy_tree(source, dest)
    stamp.write_text(current, encoding="utf-8")
    return dest


def examples_location(source: Traversable, cache: Path, platform_name: str) -> Path:
    """The folder the Examples category reads from on this platform.

    On Android it's a private copy under ``cache``. Elsewhere it's the bundled
    folder itself.
    """
    if platform_name == "android":
        return refresh_copy(source, cache / "examples")
    return Path(str(source))
