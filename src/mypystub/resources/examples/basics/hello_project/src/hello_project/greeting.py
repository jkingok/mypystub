"""Build the greeting, using the project's dependency."""

import humanize  # pyright: ignore[reportMissingImports]  # installed by the launcher


def greet(name: str, size_in_bytes: int) -> str:
    """Return a greeting that mentions a human-readable size."""
    return f"Hello {name}! This project is {humanize.naturalsize(size_in_bytes)}."
