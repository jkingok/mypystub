from pathlib import Path
import shutil
import toga

shutil.rmtree(Path(toga.App.app.paths.cache) / "site_packages")