"""Shared pytest setup for desktop runs and Briefcase's on-device test runner."""

import sys
from pathlib import Path

# On desktop the app package lives under src/; on device it is already importable.
SRC = Path(__file__).parent.parent / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
