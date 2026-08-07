import importlib
from importlib.metadata import distributions
import importlib.util
from pathlib import Path
import re
import shutil
import sys
import zipfile

# Use the modern native TOML parser
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # Fallback for older environments


def get_bundled_app_packages() -> set[str]:
    """Scans the Briefcase app_packages directory on sys.path for installed package names."""
    # Locate the app_packages entry in sys.path
    app_packages_path = next(
        (Path(p) for p in sys.path if p.endswith("app_packages")), None
    )

    if not app_packages_path or not app_packages_path.exists():
        return set()

    # Query importlib.metadata specifically for distributions inside app_packages
    bundled_names = set()
    for dist in distributions(path=[str(app_packages_path)]):
        # Canonicalize package names to lowercase (e.g. 'HTTPX' -> 'httpx')
        bundled_names.add(dist.metadata["Name"].lower())

    return bundled_names


def get_pip():
    from resolvelib import BaseReporter, Resolver
    from resolvelib.providers import AbstractProvider
    from unearth import PackageFinder, TargetPython

    # -------------------------------------------------------------------------
    # 1. Define the Resolvelib Provider using Unearth's Finder
    # -------------------------------------------------------------------------
    class LauncherDependencyProvider(AbstractProvider):
        def __init__(self, finder: PackageFinder):
            self.finder = finder

        def identify(self, requirement_or_candidate):
            # Requirements are usually strings or unearth Requirement objects
            return requirement_or_candidate

        def get_preference(
            self, identifier, resolutions, candidates, information, backtrack_causes
        ):
            # Extract the sequence for this identifier from the candidates map
            current_candidates = candidates.get(identifier, [])

            # If it's an itertools.chain object or an iterator, convert it to a list
            # so Python can safely evaluate its length
            if not isinstance(current_candidates, (list, tuple)):
                current_candidates = list(current_candidates)

            return len(current_candidates)

        def find_matches(self, identifier, requirements, incompatibilities):
            # 1. Gather all potential release matches for this package ID
            all_matches = self.finder.find_matches(identifier, allow_prereleases=False)

            # 2. Filter the matches strictly down to valid, applicable wheel files
            wheel_candidates = []
            for match in all_matches:
                if match.link.filename.endswith(".whl"):
                    wheel_candidates.append(match)

            # 3. Return the filtered list of packages to the resolver.
            # (If you want just the single best wheel candidate, you can sort or pick the first)
            if wheel_candidates:
                # unearth automatically orders find_all_matches from best/newest to worst
                return [wheel_candidates[0]]

            print(f"⚠️ Warning: No compatible pure-Python .whl found for {identifier}!")
            return []

        def is_satisfied_by(self, requirement, candidate):
            # Simplified validation matching version strings
            return True

        def get_dependencies(self, candidate):
            # candidate is the unearth 'Package' object pinned by the resolver.
            # We spin up unearth's internal metadata provider to read its requirements array cleanly.
            try:
                metadata_provider = self.finder.make_provider(candidate)
                return metadata_provider.get_dependencies(candidate)
            except Exception:
                # Fallback if a candidate has no dependencies or lacks metadata
                return []

    # -------------------------------------------------------------------------
    # 2. Main Pip-Like Downloader Engine
    # -------------------------------------------------------------------------
    def sync_launcher_dependencies(dependencies: list, output_dir: str):
        target_path = Path(output_dir)
        target_path.mkdir(parents=True, exist_ok=True)

        bundled_packages = get_bundled_app_packages()

        def get_req_name(req_str: str) -> str:
            # Strip specifiers like 'httpx>=0.20.0' or 'httpx[http2]' down to 'httpx'
            name = re.split(r"[<=><!=~;\[\s]", str(req_str))[0].strip().lower()
            return name

        # Keep only dependencies that aren't already in app_packages
        needed_dependencies = [
            dep for dep in dependencies if get_req_name(dep) not in bundled_packages
        ]

        if not needed_dependencies:
            print("✅ All required packages are already provided by the app runtime.")
            return

        # B. Explicitly target pure-Python environment matching iOS execution contexts
        running_version = sys.version_info[:2]
        # We restrict target tags to 'py3' and 'none' (any architecture)
        target_env = TargetPython(
            py_ver=running_version,  # Match your runtime Python version
            platforms=["any"],
            impl="py",
        )

        finder = PackageFinder(
            index_urls=["https://pypi.org/simple/"], target_python=target_env
        )

        # C. Execute tree resolution
        provider = LauncherDependencyProvider(finder)

        # Pass an instance of BaseReporter as the required argument
        reporter = BaseReporter()
        resolver = Resolver(provider, reporter)

        print("🔍 Resolving dependency tree graph...")
        result = resolver.resolve(dependencies)

        # D. Download and extract wheels
        # Temporary cache workspace for raw .whl archives
        download_cache = target_path / ".cache"
        download_cache.mkdir(exist_ok=True)

        for name, candidate in result.mapping.items():
            print(f"⬇️ Fetching candidate: {candidate.name}=={candidate.version}")

            # E. Download the file archive securely using unearth's httpx session handler
            link = candidate.link
            wheel_filename = link.filename
            wheel_path = download_cache / wheel_filename

            # Instead of finder.session.get(..., stream=True), use finder.session.stream("GET", ...)
            with finder.session.stream("GET", link.url) as response:
                # Check that the download link is happy and valid
                response.raise_for_status()

                with open(wheel_path, "wb") as whl_file:
                    # iter_bytes() streams chunks out of memory to keep iOS happy
                    for chunk in response.iter_bytes():
                        whl_file.write(chunk)

            # Unearth gives us a precise link asset to download
            link = candidate.link
            wheel_filename = link.filename
            wheel_path = download_cache / wheel_filename

            # F. Unpack the Wheel directly to your runtime folder
            print(f"🔓 Extracting {wheel_filename} to target directory...")
            with zipfile.ZipFile(wheel_path, "r") as zip_ref:
                # We filter out metadata directories to avoid cluttering app paths
                for file_info in zip_ref.infolist():
                    if not (
                        file_info.filename.endswith(".dist-info/")
                        or file_info.filename.endswith(".egg-info/")
                    ):
                        zip_ref.extract(file_info, target_path)

        # Clean up file cache residues
        shutil.rmtree(download_cache)
        print("✅ Complete! All packages available in target workspace.")

    def sync_launcher_dependencies_via_toml(pyproject_path: str, output_dir: str):
        pyproject = Path(pyproject_path)

        # A. Read dependencies from pyproject.toml
        with pyproject.open("rb") as f:
            config = tomllib.load(f)

        # Target dependencies under [project] dependencies array (PEP 621)
        dependencies = config.get("project", {}).get("dependencies", [])
        if not dependencies:
            print(
                "No dependencies found in pyproject.toml under [project.dependencies]."
            )
            return

        print(f"📦 Found root requirements: {dependencies}")
        return sync_launcher_dependencies(dependencies, output_dir)

    # Example Usage:
    # sync_launcher_dependencies("pyproject.toml", "src/launcher/packages")
    return sync_launcher_dependencies


# The official master manifest of required core runtime modules
CORE_MANIFEST = {
    "certifi": "certifi-*-py3-none-any.whl",
    "h11": "h11-*-py3-none-any.whl",
    "httpcore": "httpcore-*-py3-none-any.whl",
    "httpx": "httpx-*-py3-none-any.whl",
    "idna": "idna-*-py3-none-any.whl",
    "packaging": "packaging-*-py3-none-any.whl",
    "resolvelib": "resolvelib-*-py3-none-any.whl",
    "unearth": "unearth-*-py3-none-any.whl",
}


def strict_manifest_preflight(prefix=None):
    # app_root = Path(__file__).resolve().parent
    if not prefix:
        prefix = Path("~/Documents").expanduser()
    bootstrap_cache_dir = prefix / "wheels"
    target_user_packages = prefix / "site_packages"

    # Ensure local path is mapped
    target_user_packages.mkdir(parents=True, exist_ok=True)
    if str(target_user_packages) not in sys.path:
        sys.path.insert(0, str(target_user_packages))

    print("\n================ SYSTEM PREFLIGHT CHECK ================")

    missing_from_runtime = {}
    wheels_to_unpack = []
    download_instruction_triggered = False

    # 1. Evaluate environment against the strict absolute manifest
    for module_name, wheel_pattern in CORE_MANIFEST.items():
        # Check if Python can find this module active anywhere right now
        spec = importlib.util.find_spec(module_name)

        if spec is not None:
            print(f"  [✓] Python Import: '{module_name}' is active.")
        else:
            print(f"  [✗] Python Import: '{module_name}' is MISSING!")
            missing_from_runtime[module_name] = wheel_pattern

    # 2. Resolution Phase: For anything missing, check if we have the wheel to fix it
    if missing_from_runtime:
        print("\n----------------- RESOLVING GAPS -----------------")

        for missing_mod, pattern in missing_from_runtime.items():
            # Look in our bundled installer bootstrap cache folder
            cached_wheels = (
                list(bootstrap_cache_dir.glob(pattern))
                if bootstrap_cache_dir.exists()
                else []
            )

            if cached_wheels:
                # We found a matching wheel file in the installer cache bundle!
                chosen_wheel = cached_wheels[0]
                print(
                    f"  [Found Cache] Using bundled archive to heal '{missing_mod}':\n                -> {chosen_wheel.name}"
                )
                wheels_to_unpack.append(chosen_wheel)
            else:
                # CRITICAL: The wheel file isn't even in the project source tree!
                if not download_instruction_triggered:
                    print("\n!!! BUILD ERROR: MISSING ASSETS DETECTED !!!")
                    print(
                        "You need to download the following pure-Python wheels from PyPI"
                    )
                    print("and place them inside the 'wheels' folder:\n")
                    download_instruction_triggered = True

                print(f"  --> DOWNLOAD REQUIRED: {pattern.replace('*', '[version]')}")

    # 3. Execution Phase: If we have the wheels, gently unpack only the missing targets
    if wheels_to_unpack:
        print(
            f"\n[Bootstrap] Unpacking {len(wheels_to_unpack)} required modules to user_packages..."
        )
        for wheel_path in wheels_to_unpack:
            try:
                print(f"  -> Unzipping: {wheel_path.name}")
                with zipfile.ZipFile(wheel_path, "r") as zip_ref:
                    zip_ref.extractall(target_user_packages)
            except Exception as e:
                print(f"  [!] Failed to extract {wheel_path.name}: {e}")
                return False
        print("[Bootstrap] Local environment healed successfully.\n")
        return True

    # 4. Final Verdict
    if download_instruction_triggered:
        print("\n========================================================")
        print("Preflight halted: Complete your bootstrap cache directory above.")
        print("========================================================\n")
        return False

    print("========================================================")
    print("All internal core runtime dependencies verified clean.")
    print("========================================================\n")
    return True


def scan_all_prototypes(base_dir_path):
    compiled_items = []
    base_dir = Path(base_dir_path)

    if not base_dir.exists():
        return compiled_items

    # Loop through everything inside the directory
    for item in sorted(base_dir.iterdir(), key=lambda x: x.name.lower()):
        # Skip hidden files/folders (like .DS_Store or system bits)
        if item.name.startswith("."):
            continue

        # --- CASE A: The "Toy Script" (Loose .py file) ---
        if item.is_file() and item.suffix == ".py":
            # Don't accidentally auto-load your main launcher scripts
            if item.name in ["patch_app.py", "__init__.py"]:
                continue

            # Create a clean, zero-config metadata profile
            compiled_items.append(
                {
                    "title": item.stem,  # Just the filename as the title
                    "subtitle": "Standalone Python script.",
                    "icon_path": None,  # Uses default fallback icon
                    "entry_point": item,
                    "folder_root": item.parent,
                    "dependencies": [],  # Toy scripts have no extra dependencies declared
                }
            )

        # --- CASE B: The "Full Project" (Folder with pyproject.toml) ---
        elif item.is_dir():
            toml_path = item / "pyproject.toml"
            if toml_path.exists():
                try:
                    with open(toml_path, "rb") as f:
                        toml_data = tomllib.load(f)

                    # Read standard PEP 621 table
                    project_meta = toml_data.get("project", {})
                    name = project_meta.get("name", item.name)
                    desc = project_meta.get("description", "Project directory module.")

                    # Extract PEP 621 dependencies list (default to empty list if missing)
                    dependencies = project_meta.get("dependencies", [])

                    # Read tool overrides
                    tool_meta = toml_data.get("tool", {}).get("stub_launcher", {})
                    display_name = tool_meta.get("display_name", name)

                    # Target launch file path relative to its home folder
                    entry_filename = tool_meta.get("entry_point", "main.py")
                    entry_point = item / entry_filename
                    folder_root = item / tool_meta.get("import_path", "src")

                    icon_relative = tool_meta.get("icon")
                    icon_path = item / icon_relative if icon_relative else None

                    compiled_items.append(
                        {
                            "title": display_name,
                            "subtitle": desc,
                            "icon_path": icon_path,
                            "entry_point": entry_point,
                            "folder_root": folder_root,
                            "dependencies": dependencies,  # Pass the array forward
                        }
                    )
                except Exception as e:
                    print(f"Skipping malformed project folder {item.name}: {e}")

    return compiled_items
