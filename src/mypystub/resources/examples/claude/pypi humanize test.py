# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "humanize>=4.9",
# ]
# ///
# Installs the pure-Python 'humanize' package from PyPI on demand and uses it.
import humanize  # pyright: ignore[reportMissingImports]

print(
    "humanize version:",
    humanize.__version__ if hasattr(humanize, "__version__") else "unknown",
)
print("Big number:", humanize.intcomma(1234567))
print("File size:", humanize.naturalsize(5_368_709_120))
print("Ordinal:", humanize.ordinal(23))
print("Relative delta:", humanize.naturaldelta(7200))
print("Fraction:", humanize.fractional(0.75))
