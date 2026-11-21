"""Source builds work where the platform has no os.system, as on iOS."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mypystub import source_build


def test_isolated_works_without_os_system(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(os, "system")
    with source_build.isolated([], tmp_path, {}):
        assert not hasattr(os, "system")  # nothing to block, nothing added
    assert not hasattr(os, "system")  # and nothing left behind


def test_os_system_is_still_blocked_where_it_exists(tmp_path: Path) -> None:
    original = os.system
    with source_build.isolated([], tmp_path, {}), pytest.raises(OSError):
        os.system("true")
    assert os.system is original
