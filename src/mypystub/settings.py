import shutil
from pathlib import Path
from typing import Any, Self

import tomlkit  # Pure-Python style-preserving library
from toga.paths import Paths
from tomlkit.toml_document import TOMLDocument

from mypystub.run_settings import (
    EnvValue,
    RunSettings,
    sorted_env,
    split_env,
    usable_env,
    with_unset,
)

DEFAULTS_NAME = "config.toml"
CONFIG_NAME = "launcher.toml"
RUN_WITH = "run_with"  # [run_with."<key>"]: settings saved per path
ENVIRONMENT = "environment"  # [environment]: Setup's variables, inherited by all
ENVIRONMENT_UNSET = "environment_unset"  # names Setup unsets for every run
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
        if "unset" in table:
            entry["unset"] = table["unset"]
        self.config_doc[RUN_WITH][key] = entry  # type: ignore[index]
        self._save()

    def get_flag(self, name: str, default: bool) -> bool:
        """A true/false setting at the top of launcher.toml, or `default`."""
        self.config_doc = self._load()  # allow on disk changes
        value: Any = self.config_doc.get(name)
        if value is not None and hasattr(value, "unwrap"):
            value = value.unwrap()
        return value if isinstance(value, bool) else default

    def set_flag(self, name: str, value: bool) -> None:
        """Save a true/false setting."""
        self.config_doc = self._load()
        self.config_doc[name] = value
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

    def get_environment(self) -> dict[str, EnvValue]:
        """Setup's environment variables, which every run inherits.

        A name mapped to None is unset for every run.
        """
        return with_unset(
            usable_env(self.get_table(ENVIRONMENT)),
            self.get_table_value(ENVIRONMENT_UNSET),
        )

    def get_table_value(self, k: str) -> Any:
        """A top-level value as plain Python (None if absent)."""
        self.config_doc = self._load()  # allow on disk changes
        value = self.config_doc.get(k)
        if value is None:
            return None
        return value.unwrap() if hasattr(value, "unwrap") else value

    def set_environment(self, env: dict[str, EnvValue]) -> None:
        """Save Setup's environment variables, and the names it unsets."""
        self.config_doc = self._load()
        values, unset = split_env(env)
        table = tomlkit.table()
        for name, value in sorted_env(values):
            table[name] = value
        self.config_doc[ENVIRONMENT] = table
        if unset:
            self.config_doc[ENVIRONMENT_UNSET] = unset
        elif ENVIRONMENT_UNSET in self.config_doc:
            del self.config_doc[ENVIRONMENT_UNSET]
        self._save()
