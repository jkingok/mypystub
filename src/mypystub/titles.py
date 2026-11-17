"""Titles for list rows, from untrusted metadata (#235).

Kept free of Toga imports so it can be unit tested on desktop.
"""

import re

SEPARATORS = re.compile(r"[\s_.\-]+")


def clean_title(text: object) -> str | None:
    """A title from untrusted metadata: one line, trimmed; None if empty.

    It is shown as plain text, never as markup, so nothing else is done to it.
    The list row shortens a long one itself.
    """
    if not isinstance(text, str):
        return None
    line = " ".join(text.split())
    return line or None


def distinguishing_parts(names: list[str]) -> list[str]:
    """What tells each name apart: the words they don't all share at each end.

    ``app_v1`` and ``app_v2`` give ``v1`` and ``v2``; ``tool.py`` and
    ``tool_old.py`` give ``tool`` and ``old`` (a name left with nothing gets its
    whole self back). Words are split at spaces, ``_``, ``-`` and ``.``.
    """
    words = [[w for w in SEPARATORS.split(n) if w] for n in names]
    shortest = min((len(w) for w in words), default=0)
    start = 0
    while start < shortest and len({w[start].lower() for w in words}) == 1:
        start += 1
    end = 0
    while end < shortest - start and len({w[-1 - end].lower() for w in words}) == 1:
        end += 1
    parts = []
    for name, w in zip(names, words, strict=True):
        middle = w[start : len(w) - end]
        parts.append(" ".join(middle) if middle else name)
    return parts
