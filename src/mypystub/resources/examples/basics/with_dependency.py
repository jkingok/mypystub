"""Use a package from PyPI, installed on the first run."""

# /// script
# dependencies = ["humanize"]
# ///

import humanize  # pyright: ignore[reportMissingImports]  # installed by the launcher

if __name__ == "__main__":
    print(f"A gigabyte is {humanize.naturalsize(10**9)}.")
    print(f"An hour ago was {humanize.naturaltime(3600)}.")
