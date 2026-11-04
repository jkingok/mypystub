import shutil
from pathlib import Path
from typing import Any, Self

import tomlkit  # Pure-Python style-preserving library
from toga.paths import Paths
from tomlkit.toml_document import TOMLDocument

from mypystub.run_settings import RunSettings, sorted_env, usable_env

DEFAULTS_NAME = "config.toml"
CONFIG_NAME = "launcher.toml"
RUN_WITH = "run_with"  # [run_with."<key>"]: settings saved per path
ENVIRONMENT = "environment"  # [environment]: Setup's variables, inherited by all
QUICK_START = "quick_start"  # the row key offered to run at launch, if any


class Settings:
    _instance = None
    _initialized = False

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        if cls._instance is None:
            # Create the single instance and cache it on the class
            cls._instance = super().__new__(cls)
            # Initialize flags or containers that only ever happen ONCE
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, paths: Paths):
        # __init__ runs EVERY time you call,
        # so guard it to ensure it only initializes once.
        if self._initialized:
            return
        self.config_path = paths.config
        self.config_file = self.config_path / CONFIG_NAME
        self.this_path = Path(__file__).resolve().parent
        self.config_defaults = (
            self.this_path / "resources" / "templates" / DEFAULTS_NAME
        )
        self.config_doc = self._load()
        self._initialized = True

    def _load(self) -> TOMLDocument:
        if not self.config_file.exists():
            shutil.copy(self.config_defaults, self.config_file)
        with open(self.config_file, "r", encoding="utf-8") as f:
            return tomlkit.load(f)

    def _save(self) -> None:
        self.config_file.write_text(tomlkit.dumps(self.config_doc))

    def get(self, k: str) -> str:
        self.config_doc = self._load()  # allow on disk changes
        return self.config_doc[k]

    def get_table(self, k: str) -> dict:
        """An optional table such as [aliases], as a plain dict ({} if absent)."""
        self.config_doc = self._load()  # allow on disk changes
        table = self.config_doc.get(k, {})
        return table.unwrap() if hasattr(table, "unwrap") else dict(table)

    def set(self, k: str, v: str) -> None:
        self.config_doc[k] = v
        self._save()  # preserve immediately

    def get_run_with(self, key: str) -> RunSettings:
        """The Setup settings saved for `key` (in [run_with]), or empty ones."""
        return RunSettings.from_table(self.get_table(RUN_WITH).get(key))

    def set_run_with(
        self, key: str, settings: RunSettings, *, with_args: bool = True
    ) -> None:
        """Save Setup settings for `key`; without args, the environment only."""
        self.config_doc = self._load()
        if RUN_WITH not in self.config_doc:
            self.config_doc[RUN_WITH] = tomlkit.table(is_super_table=True)
        entry = tomlkit.table()
        table = settings.to_table(with_args=with_args)
        if with_args:
            entry["args"] = table["args"]
        env = tomlkit.inline_table()
        env.update(table["env"])
        entry["env"] = env
        self.config_doc[RUN_WITH][key] = entry  # type: ignore[index]
        self._save()

    def get_quick_start(self) -> str | None:
        """The row key offered to run at launch, or None if none is set."""
        self.config_doc = self._load()  # allow on disk changes
        value = self.config_doc.get(QUICK_START)
        return str(value) if isinstance(value, str) and value else None

    def set_quick_start(self, key: str | None) -> None:
        """Offer `key` at launch, or clear the setting when `key` is None."""
        self.config_doc = self._load()
        if key:
            self.config_doc[QUICK_START] = key
        elif QUICK_START in self.config_doc:
            del self.config_doc[QUICK_START]
        self._save()

    def get_environment(self) -> dict[str, str]:
        """Setup's environment variables, which every run inherits."""
        return usable_env(self.get_table(ENVIRONMENT))

    def set_environment(self, env: dict[str, str]) -> None:
        """Save Setup's environment variables."""
        self.config_doc = self._load()
        table = tomlkit.table()
        for name, value in sorted_env(env):
            table[name] = value
        self.config_doc[ENVIRONMENT] = table
        self._save()
