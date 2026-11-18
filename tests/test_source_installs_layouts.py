"""Source layouts seen in the wild, installed from their archives (#286)."""

from pathlib import Path

from mypystub import source_installs as si


def test_a_stray_init_beside_the_packages_isnt_installed(tmp_path: Path) -> None:
    """tatogalib has src/__init__.py next to src/tatogalib/: only the package goes."""
    (tmp_path / "src" / "tatogalib" / "ui").mkdir(parents=True)
    (tmp_path / "src" / "__init__.py").write_text("")
    (tmp_path / "src" / "tatogalib" / "__init__.py").write_text("")
    (tmp_path / "src" / "tatogalib" / "ui" / "__init__.py").write_text("")
    project = {"project": {"name": "tatogalib", "version": "0.9.6"}}
    found = si._find_packages(tmp_path, project)
    assert found == [tmp_path / "src" / "tatogalib"]
