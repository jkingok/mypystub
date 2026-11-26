"""Setup's debug switch is the stamp file in the cache folder (#347).

Skipped where toga_dummy isn't installed, such as on device.
"""

from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")

from mypystub import logfile, ui


def test_the_switch_creates_and_removes_the_stamp_in_the_cache(
    proto: ui.Prototype, tmp_path: Path
) -> None:
    proto.cache_path = tmp_path / "cache"
    stamp = logfile.stamp_path(proto.cache_path)
    assert not proto.debug_logs
    proto.set_debug_logs(True)
    assert stamp.exists() and proto.debug_logs
    proto.set_debug_logs(False)
    assert not stamp.exists() and not proto.debug_logs
    proto.set_debug_logs(False)  # removing nothing is fine
