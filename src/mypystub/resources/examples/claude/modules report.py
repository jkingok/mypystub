# Installed modules and import checks, standard library only.
import importlib
import importlib.util
import pkgutil
import sys

print("=== Built-in modules ===")
print("Count:", len(sys.builtin_module_names))
print(sorted(sys.builtin_module_names))

print()
print("=== Standard library modules to probe ===")
candidates = [
    "json",
    "sqlite3",
    "ssl",
    "hashlib",
    "zlib",
    "lzma",
    "bz2",
    "ctypes",
    "curses",
    "readline",
    "tkinter",
    "decimal",
    "fractions",
    "statistics",
    "uuid",
    "secrets",
    "zoneinfo",
    "asyncio",
    "socket",
    "urllib.request",
    "http.client",
    "email",
    "xml.etree.ElementTree",
    "csv",
    "sqlite3",
    "multiprocessing",
    "threading",
    "tomllib",
]
seen = set()
for name in candidates:
    if name in seen:
        continue
    seen.add(name)
    try:
        spec = importlib.util.find_spec(name)
        status = "present" if spec is not None else "missing"
    except (ImportError, ValueError) as err:
        status = "error: " + type(err).__name__
    print(f"{name:28} {status}")

print()
print("=== Top-level modules on sys.path ===")
names = sorted({m.name for m in pkgutil.iter_modules() if not m.name.startswith("_")})
print("Total:", len(names))
for name in names[:40]:
    print(" ", name)

print()
print("=== Loaded modules ===")
print("Currently in sys.modules:", len(sys.modules))
