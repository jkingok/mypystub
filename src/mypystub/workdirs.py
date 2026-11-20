"""Where a run's working directory is: a per-script choice in Setup (#308).

A run's code always comes from where it is (``__file__``, ``sys.argv[0]`` and
its import root are unchanged); only ``os.getcwd()`` moves, so relative reads
and writes go to the chosen folder. Choices are saved as text, never absolute
paths, since iOS moves the app's folders between installs:

- ``"script"``: the script's own folder (or the project folder), as before;
- ``"cache"``: a folder of its own in the app's cache, made when the run
  starts. For the bundled Examples, which are read-only; may be cleared by the
  system or Setup's Wipe, so it's for scratch output;
- ``"documents:<relative path>"``: a folder in Documents.

A thing with no choice inherits one: from its package, then its category's
Setup, then the category's built-in default (Examples: the cache; Documents:
the script's folder).

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

SCRIPT, CACHE = "script", "cache"
DOCUMENTS_PREFIX = "documents:"
CACHE_FOLDER = "workdirs"
# A category's choice when its Setup doesn't set one
CATEGORY_DEFAULTS = {"Examples": CACHE}


def documents(relative: str | PurePosixPath = "") -> str:
    """The choice for a folder in Documents ("" for Documents itself)."""
    path = PurePosixPath(relative).as_posix()
    return DOCUMENTS_PREFIX + ("" if path == "." else path)


def is_valid(choice: str | None) -> bool:
    """Whether `choice` is a choice this module understands."""
    if choice in (SCRIPT, CACHE):
        return True
    if not choice or not choice.startswith(DOCUMENTS_PREFIX):
        return False
    path = PurePosixPath(choice[len(DOCUMENTS_PREFIX) :])
    return not path.is_absolute() and ".." not in path.parts


def default_for(category: str | None) -> str:
    """A category's built-in choice."""
    return CATEGORY_DEFAULTS.get(category or "", SCRIPT)


def describe(choice: str) -> str:
    """The choice in words, for Setup and the Script tab."""
    if choice == CACHE:
        return "Cache"
    if choice.startswith(DOCUMENTS_PREFIX):
        parts = PurePosixPath(choice[len(DOCUMENTS_PREFIX) :]).parts
        return " › ".join(("Documents", *parts))
    return "Script's folder"


def resolve(
    choice: str,
    *,
    script_folder: Path,
    cache: Path,
    documents_root: Path,
    key: str,
) -> tuple[Path, str | None]:
    """The folder a run works in, made if need be, and a notice if any.

    `key` is the thing's settings key (its category and path), which names its
    own cache folder. A Documents folder that's gone falls back to the script's
    folder, with a notice saying so.
    """
    if choice == CACHE:
        folder = cache / CACHE_FOLDER / safe_name(key)
        folder.mkdir(parents=True, exist_ok=True)
        return folder, None
    if choice.startswith(DOCUMENTS_PREFIX) and is_valid(choice):
        folder = documents_root / choice[len(DOCUMENTS_PREFIX) :]
        if folder.is_dir():
            return folder, None
        return script_folder, (
            f"The working folder {describe(choice)} isn't there any more, so this "
            "run uses the script's own folder. Choose another in its Setup."
        )
    return script_folder, None


def safe_name(key: str) -> str:
    """A folder path from a settings key: its parts, with ``:`` for entry points."""
    parts = [
        part for part in key.replace(":", "/").split("/") if part not in ("", ".", "..")
    ]
    return "/".join(parts) or "default"
