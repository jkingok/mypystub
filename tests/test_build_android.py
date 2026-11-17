"""Tests for scripts/build_android.py, which builds and signs an Android APK."""

import importlib.util
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "build_android.py"

pytestmark = pytest.mark.skipif(
    not SCRIPT.exists(), reason="scripts/ is not bundled on device"
)


def load():
    """Import the script as a module."""
    spec = importlib.util.spec_from_file_location("build_android", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_default_python_is_named_too() -> None:
    script = load()
    assert script.overrides(script.DEFAULT_PYTHON)[1] == 'bundle="au.id.jking.py315"'


def test_plain_keeps_the_normal_app_id() -> None:
    assert load().overrides("3.14", plain=True) == []


def test_another_python_gets_its_own_bundle_and_name() -> None:
    assert load().overrides("3.14") == [
        "-C",
        'bundle="au.id.jking.py314"',
        "-C",
        'formal_name="MyPyStub 3.14"',
    ]


def test_signing_reads_passwords_from_the_environment() -> None:
    env = {
        "ANDROID_KEYSTORE": "/k.jks",
        "ANDROID_KEY_ALIAS": "key",
        "ANDROID_KEYSTORE_PASSWORD": "secret",
    }
    command = load().sign_command(Path("signer"), Path("a.apk"), Path("s.apk"), env)
    assert "env:ANDROID_KEYSTORE_PASSWORD" in command
    assert "--key-pass" not in command  # the key shares the keystore's password
    assert "secret" not in " ".join(command)
    assert command[-3:] == ["--out", "s.apk", "a.apk"]


def test_a_separate_key_password_is_passed_as_a_reference() -> None:
    env = {
        "ANDROID_KEYSTORE": "/k.jks",
        "ANDROID_KEY_ALIAS": "key",
        "ANDROID_KEYSTORE_PASSWORD": "a",
        "ANDROID_KEY_PASSWORD": "b",
    }
    command = load().sign_command(Path("signer"), Path("a.apk"), Path("s.apk"), env)
    assert command[command.index("--key-pass") + 1] == "env:ANDROID_KEY_PASSWORD"


def test_a_missing_password_is_an_error_not_a_prompt() -> None:
    env = {"ANDROID_KEYSTORE": "/k.jks", "ANDROID_KEY_ALIAS": "key"}
    with pytest.raises(SystemExit, match="ANDROID_KEYSTORE_PASSWORD"):
        load().sign_command(Path("signer"), Path("a.apk"), Path("s.apk"), env)


def test_the_name_has_the_python_and_the_version() -> None:
    assert load().apk_name("3.14", "2026.11.13.1") == "MyPyStub_314-2026.11.13.1.apk"


def test_the_version_comes_from_the_briefcase_section() -> None:
    script = load()
    version = script.app_version()
    assert version[0].isdigit()
    assert f'version = "{version}"' in (ROOT / "pyproject.toml").read_text()


def test_the_one_new_apk_is_found_beside_older_ones(tmp_path: Path) -> None:
    script = load()
    old = tmp_path / "MyPyStub-1.apk"
    old.write_text("x")
    before = script.apks(tmp_path)
    new = tmp_path / "MyPyStub 3.14-2.apk"
    new.write_text("x")
    assert script.new_apk(before, tmp_path) == new


def test_a_rewritten_apk_counts_as_new(tmp_path: Path) -> None:
    script = load()
    apk = tmp_path / "MyPyStub-1.apk"
    apk.write_text("x")
    os.utime(apk, (1, 1))
    before = script.apks(tmp_path)
    os.utime(apk, (2, 2))
    assert script.new_apk(before, tmp_path) == apk


@pytest.mark.parametrize("count", [0, 2])
def test_zero_or_several_new_apks_is_an_error(tmp_path: Path, count: int) -> None:
    script = load()
    for index in range(count):
        (tmp_path / f"{index}.apk").write_text("x")
    with pytest.raises(SystemExit, match="one new APK"):
        script.new_apk({}, tmp_path)


def test_the_newest_build_tools_apksigner_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for version in ("9.0.0", "34.0.0", "36.1.0"):
        tool = tmp_path / "build-tools" / version / "apksigner"
        tool.parent.mkdir(parents=True)
        tool.write_text("")
    monkeypatch.setenv("ANDROID_HOME", str(tmp_path))
    assert load().apksigner() == tmp_path / "build-tools" / "36.1.0" / "apksigner"


def test_briefcases_own_sdk_is_used_when_android_home_is_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = load()
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.setattr(
        script, "sdk_roots", lambda home=None: [tmp_path / "none", tmp_path / "sdk"]
    )
    tool = tmp_path / "sdk" / "build-tools" / "36.0.0" / "apksigner"
    tool.parent.mkdir(parents=True)
    tool.write_text("")
    assert script.apksigner() == tool


def test_android_home_alone_wins_when_it_is_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANDROID_HOME", str(tmp_path))
    assert load().sdk_roots() == [tmp_path]


def test_without_android_home_briefcases_cache_comes_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    first, second = load().sdk_roots(tmp_path)
    assert first.parts[-2:] == ("tools", "android_sdk")
    assert "org.beeware.briefcase" in str(first)
    assert second == tmp_path / "Library/Android/sdk"
