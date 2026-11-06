"""The URL helpers for wheels named by a requirement (#171)."""

from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.tags import Tag
from packaging.version import Version

from mypystub import direct_refs

ANY = {Tag("py3", "none", "any")}


def test_url_filename_ignores_fragment_and_decodes() -> None:
    """The name is the last path segment, without ``#...`` and with %-escapes."""
    url = "https://h/p/foo-1.0-py3-none-any.whl#sha256=ab"
    assert direct_refs.url_filename(url) == "foo-1.0-py3-none-any.whl"
    assert direct_refs.url_filename("https://h/a%20b.whl") == "a b.whl"


def test_expected_sha256() -> None:
    """Only a 64-hex ``sha256=`` fragment counts, whatever its case."""
    digest = "AB" * 32
    assert (
        direct_refs.expected_sha256(f"https://h/x.whl#sha256={digest}")
        == digest.lower()
    )
    assert direct_refs.expected_sha256("https://h/x.whl#sha256=short") is None
    assert direct_refs.expected_sha256("https://h/x.whl") is None


def test_wheel_identity_is_name_and_version() -> None:
    """A matching name (any spelling) gives the wheel's own name and version."""
    req = Requirement("Foo_Bar @ https://h/foo_bar-2.0-py3-none-any.whl")
    assert direct_refs.wheel_identity(req, ANY) == ("foo-bar", Version("2.0"))


def test_check_sha256_reads_the_file(tmp_path: Path) -> None:
    """The file's real hash is compared with the URL's."""
    path = tmp_path / "x.whl"
    path.write_bytes(b"abc")
    good = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    direct_refs.check_sha256(path, f"https://h/x.whl#sha256={good}")
    direct_refs.check_sha256(path, "https://h/x.whl")  # no hash asked for
    with pytest.raises(direct_refs.WheelProblem):
        direct_refs.check_sha256(path, f"https://h/x.whl#sha256={'0' * 64}")
