"""A prototype that replaces ``app.settings`` must not break the launcher.

Prototypes run in the launcher's process and share its Toga app object. Some
examples set ``app.settings`` to their own settings class; the launcher once
read its settings back from there, so the next tap failed with
"'Settings' object has no attribute 'get_run_with'".

Skipped where toga_dummy isn't installed, such as on device.
"""

import os
from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import ui
from tests.support_ui import row, run_to_end


class TheirSettings:
    """What an example's own settings class offers: not the launcher's methods."""

    def get(self, key: str) -> str:
        return ""


def test_launcher_ignores_a_prototype_replacing_app_settings(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Settings, aliases and runs keep using the launcher's own settings."""
    mine = proto.settings
    monkeypatch.setattr(app, "settings", TheirSettings(), raising=False)
    assert proto.settings is mine
    assert proto.configured_aliases() == {}
    settings, env = proto.run_settings_for(row(proto, "top"))
    assert settings.args == [] and env == {}
    run_to_end(proto, app, docs, "x = 1\n", monkeypatch)
    assert proto.tabs.current_tab.text == "List"
