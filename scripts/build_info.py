"""Record the branch and ``git describe`` for the build to bundle.

Fastlane runs this before every Briefcase build. Run it yourself before a local
``briefcase run`` so About shows the branch you built, not an older one::

    uv run scripts/build_info.py

Writes ``src/mypystub/resources/build_info.json`` (ignored by Git). Outside a Git
repository it removes the file, so nothing stale is bundled.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mypystub import build_info


def main() -> None:
    """Write the file, or remove it when Git can't say."""
    info = build_info.from_git(build_info.REPO)
    if info is None:
        build_info.INFO_FILE.unlink(missing_ok=True)
        print("No Git information; build_info.json removed")
        return
    build_info.write(info)
    print(f"{info.branch} {info.describe}")


if __name__ == "__main__":
    main()
