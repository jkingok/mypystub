"""Media Hub starts from its defaults, so a first run has every setting it reads."""

import re
import tomllib
from pathlib import Path

PACKAGE = (
    Path(__file__).parent.parent
    / "src/mypystub/resources/examples/joshua/media_hub/src/media_hub"
)
READ = re.compile(r"settings\.get\(\s*\"(\w+)\"")


def test_every_setting_it_reads_has_a_default() -> None:
    """Settings.get raises KeyError for a key the defaults leave out."""
    read = {
        key for path in PACKAGE.glob("*.py") for key in READ.findall(path.read_text())
    }
    defaults = tomllib.loads((PACKAGE / "resources/templates/config.toml").read_text())
    assert read >= {"page_title", "tmdb_api_key"}
    assert read <= set(defaults)
