"""Build, and optionally sign, an Android APK with a chosen Python.

    uv run scripts/build_android.py 3.14

Each Python gets its own app ID and name (``au.id.jking.py314.mypystub``,
"MyPyStub 3.14"), the default Python included, so APKs built with different
Pythons install side by side. ``--plain`` keeps the normal app ID and name
(``au.id.jking.mypystub``, "MyPyStub"), which updates a Fastlane build.

Steps: generate the icons, record the branch for About, clear the old Android build (Briefcase won't
overwrite it), pin Toga's git requirements to their current commit (as Fastlane
does, so pip reuses its cached wheels instead of cloning Toga for each package;
pyproject.toml is put back afterwards), ``briefcase create``, ``briefcase package
-p apk``, then sign the
APK with the SDK's ``apksigner`` if the signing variables are set:

    ANDROID_KEYSTORE            path to the keystore
    ANDROID_KEY_ALIAS           the key's alias
    ANDROID_KEYSTORE_PASSWORD   the keystore password (read from the environment,
                                so apksigner doesn't stop to ask for it)
    ANDROID_KEY_PASSWORD        the key's password; only if it differs

The APK is renamed from Briefcase's generic name to ``MyPyStub_314-<version>.apk``
(the Python without its dot, then the version), and signed into
``MyPyStub_314-<version>-signed.apk``. Without ``ANDROID_KEYSTORE`` the unsigned
APK is left in ``dist/``. ``apksigner`` also writes a ``.idsig`` file beside the
signed one; installing doesn't need it.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PYTHON = "3.15"  # the Python Fastlane builds with
BUNDLE = "au.id.jking"
FORMAL_NAME = "MyPyStub"
APP = "mypystub"


def overrides(python: str, plain: bool = False) -> list[str]:
    """The ``-C`` options naming the app for `python`; none when `plain`.

    Briefcase can't override ``app_name``, so the bundle and formal name carry
    the Python. Values are read as TOML, so strings are quoted. A plain build
    keeps the normal app ID, so it updates a Fastlane build of the app.
    """
    if plain:
        return []
    tag = "py" + python.replace(".", "")
    return [
        "-C",
        f'bundle="{BUNDLE}.{tag}"',
        "-C",
        f'formal_name="{FORMAL_NAME} {python}"',
    ]


def apk_name(python: str, version: str) -> str:
    """The distinct name for an APK: ``MyPyStub_314-2026.11.13.1.apk``."""
    return f"{FORMAL_NAME}_{python.replace('.', '')}-{version}.apk"


def app_version(pyproject: Path = ROOT / "pyproject.toml") -> str:
    """The version Briefcase puts in the APK, from ``[tool.briefcase]``."""
    with pyproject.open("rb") as file:
        return tomllib.load(file)["tool"]["briefcase"]["version"]


def apks(dist: Path) -> dict[Path, float]:
    """Each APK in `dist` with when it was last written."""
    return {p: p.stat().st_mtime for p in dist.glob("*.apk")}


def new_apk(before: dict[Path, float], dist: Path) -> Path:
    """The one APK Briefcase just wrote: new, or rewritten, since `before`.

    Briefcase gives it a generic name, so it can't be picked by name, and an
    older build of the same app may sit beside it. SystemExit unless exactly one
    APK is new, rather than guess.
    """
    changed = [p for p, when in apks(dist).items() if before.get(p) != when]
    if len(changed) != 1:
        found = ", ".join(p.name for p in changed) or "none"
        raise SystemExit(
            f"Expected one new APK in dist/ from Briefcase, found: {found}"
        )
    return changed[0]


def sdk_roots(home: Path | None = None) -> list[Path]:
    """The Android SDKs to look in, best first.

    ``ANDROID_HOME`` (or ``ANDROID_SDK_ROOT``) alone when it is set. Otherwise
    the SDK Briefcase downloaded into its cache, then the Android Studio one.
    Briefcase's cache is where ``platformdirs`` puts a user cache for
    ``org.beeware.briefcase``: ``~/Library/Caches/`` on a Mac, ``~/.cache/`` on
    Linux, and under ``%LOCALAPPDATA%`` on Windows.
    """
    sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if sdk:
        return [Path(sdk)]
    home = home or Path.home()
    try:
        import platformdirs

        cache = platformdirs.user_cache_path("org.beeware.briefcase")
    except ImportError:
        cache = home / "Library/Caches/org.beeware.briefcase"
    return [cache / "tools" / "android_sdk", home / "Library/Android/sdk"]


def apksigner(home: Path | None = None) -> Path | None:
    """The newest build-tools' apksigner in the first Android SDK that has one."""

    def version(path: Path) -> tuple[int, ...]:
        return tuple(int(n) for n in re.findall(r"\d+", path.parent.name))

    for root in sdk_roots(home):
        # apksigner.bat on Windows
        found = [
            p
            for p in (root / "build-tools").glob("*/apksigner*")
            if p.name in ("apksigner", "apksigner.bat")
        ]
        if found:
            return max(found, key=version)
    return None


def sign_command(
    signer: Path, apk: Path, signed: Path, env: dict[str, str]
) -> list[str]:
    """The apksigner command, or SystemExit saying which variables are missing.

    Passwords are given as ``env:`` references, never on the command line, and
    the key password is left out when it is the keystore's.
    """
    missing = [
        name
        for name in ("ANDROID_KEY_ALIAS", "ANDROID_KEYSTORE_PASSWORD")
        if not env.get(name)
    ]
    if missing:
        raise SystemExit(
            f"Set {', '.join(missing)} to sign with {env['ANDROID_KEYSTORE']}"
        )
    command = [
        str(signer),
        "sign",
        "--ks",
        env["ANDROID_KEYSTORE"],
        "--ks-key-alias",
        env["ANDROID_KEY_ALIAS"],
        "--ks-pass",
        "env:ANDROID_KEYSTORE_PASSWORD",
    ]
    if env.get("ANDROID_KEY_PASSWORD"):
        command += ["--key-pass", "env:ANDROID_KEY_PASSWORD"]
    return command + ["--out", str(signed), str(apk)]


def pin_requirements(pyproject: Path) -> None:
    """Pin the git requirements in ``pyproject`` with pin_git_requirements.py."""
    script = ROOT / "scripts" / "pin_git_requirements.py"
    subprocess.run(
        [
            "uv",
            "--directory",
            str(ROOT),
            "run",
            str(script),
            "--pyproject",
            str(pyproject),
        ],
        check=True,
    )


@contextmanager
def pinned(
    pyproject: Path, pin: Callable[[Path], None] = pin_requirements
) -> Iterator[None]:
    """Pin ``pyproject``'s git requirements for the block, then restore it."""
    original = pyproject.read_bytes()
    try:
        pin(pyproject)
        yield
    finally:
        pyproject.write_bytes(original)


def briefcase(python: str, *args: str) -> None:
    """Run Briefcase under `python`, from the repository root."""
    command = ["uvx", "--python", python, "--directory", str(ROOT), "briefcase", *args]
    subprocess.run(command, check=True)


def main(argv: list[str] | None = None) -> None:
    """Build the APK, then sign it when the signing variables are set."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument(
        "python", nargs="?", default=DEFAULT_PYTHON, help="Python version, e.g. 3.14"
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="keep the normal app ID and name, to update a Fastlane build",
    )
    args = parser.parse_args(argv)
    python = args.python
    options = overrides(python, args.plain)

    # What Fastlane runs before a build: the icons, which are generated and not
    # in Git (without them the app gets Briefcase's default), and the build info
    for script in ("generate_icons.py", "scripts/build_info.py"):
        subprocess.run(["uv", "--directory", str(ROOT), "run", script], check=True)
    shutil.rmtree(ROOT / "build" / APP / "android", ignore_errors=True)
    dist = ROOT / "dist"
    before = apks(dist)
    with pinned(ROOT / "pyproject.toml"):
        briefcase(python, "create", "android", "gradle", "--no-input", *options)
        briefcase(python, "package", "android", "-p", "apk", "--no-input", *options)

    # Rename it, so builds with different Pythons don't share or replace a name
    apk = dist / apk_name(python, app_version())
    new_apk(before, dist).replace(apk)
    if not os.environ.get("ANDROID_KEYSTORE"):
        print(
            f"Unsigned APK: {apk}\nSet ANDROID_KEYSTORE to sign it, or see the README."
        )
        return
    signer = apksigner()
    if signer is None:
        raise SystemExit(
            "apksigner not found in "
            + ", ".join(str(root) for root in sdk_roots())
            + "; set ANDROID_HOME to an Android SDK with build-tools"
        )
    signed = apk.with_name(
        apk.stem + "-signed.apk"
    )  # MyPyStub_314-<version>-signed.apk
    subprocess.run(sign_command(signer, apk, signed, dict(os.environ)), check=True)
    print(f"Signed APK: {signed}")


if __name__ == "__main__":
    sys.exit(main())
