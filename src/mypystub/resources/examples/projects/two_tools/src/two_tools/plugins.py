"""Entry points in a group of their own, as a plugin system would declare."""

SETTINGS = {"colour": "blue"}


def hello() -> None:
    """Say hello from a plugin entry point."""
    print(f"Hello from a plugin. Its settings: {SETTINGS}")
