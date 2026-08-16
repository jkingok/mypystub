import shutil
from pathlib import Path

import toga

if toga.App.app:
    shutil.rmtree(Path(toga.App.app.paths.cache) / "site_packages")
