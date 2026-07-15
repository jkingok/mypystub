from pathlib import Path
import shutil
import tomlkit  # Pure-Python style-preserving library

DEFAULTS_NAME="config.toml"
CONFIG_NAME="launcher.toml"

class Settings:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            # Create the single instance and cache it on the class
            cls._instance = super().__new__(cls)
            # Initialize flags or containers that only ever happen ONCE
            cls._instance._initialized = False
        return cls._instance
 
    def __init__(self, paths):
        # __init__ runs EVERY time you call, 
        # so guard it to ensure it only initializes once.
        if self._initialized:
            return
        self.config_path = paths.config
        self.config_file = self.config_path / CONFIG_NAME
        self.this_path = Path(__file__).resolve().parent
        self.config_defaults = self.this_path / "resources" / "templates" / DEFAULTS_NAME
        self.config_doc = None
        self.load()
        self._initialized = True

    def load(self):
        if not self.config_file.exists():
            shutil.copy(self.config_defaults, self.config_file)
        with open(self.config_file, "r", encoding="utf-8") as f:
            self.config_doc = tomlkit.load(f)

    def save(self):
        self.config_file.write_text(tomlkit.dumps(self.config_doc))

    def get(self, k):
        self.load() # allow on disk changes
        return self.config_doc[k]

    def set(self, k, v):
        self.config_doc[k] = v
        self.save() # preserve immediately
