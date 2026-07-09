import importlib
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tomllib
import zipfile

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

        def get_preference(self, identifier, resolutions, candidates, information, backtrack_causes):
            # Extract the sequence for this identifier from the candidates map
            current_candidates = candidates.get(identifier, [])
        
            # If it's an itertools.chain object or an iterator, convert it to a list 
            # so Python can safely evaluate its length
            if not isinstance(current_candidates, (list, tuple)):
                current_candidates = list(current_candidates)
            
            return len(current_candidates)
            
        def find_matches(self, identifier, requirements, incompatibilities):
            # 1. Gather all potential release matches for this package ID
            all_matches = self.finder.find_matches(identifier)
        
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
         
        # B. Explicitly target pure-Python environment matching iOS execution contexts
        running_version = sys.version_info[:2]
        # We restrict target tags to 'py3' and 'none' (any architecture)
        target_env = TargetPython(
            py_ver=running_version,  # Match your runtime Python version
            platforms=["any"],
            impl="py",
        )

        finder = PackageFinder(
            index_urls=["https://pypi.org/simple/"],
            target_python=target_env
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
                    if not (file_info.filename.endswith(".dist-info/") or file_info.filename.endswith(".egg-info/")):
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
            print("No dependencies found in pyproject.toml under [project.dependencies].")
            return

        print(f"📦 Found root requirements: {dependencies}")
        return sync_launcher_dependencies(dependencies, output_dir)

    # Example Usage:
    # sync_launcher_dependencies("pyproject.toml", "src/launcher/packages")
    return sync_launcher_dependencies


# The official master manifest of required core runtime modules
CORE_MANIFEST = {
    "installer": "installer-*-py3-none-any.whl",
    "unearth": "unearth-*-py3-none-any.whl",
    "resolvelib": "resolvelib-*-py3-none-any.whl",
    "packaging": "packaging-*-py3-none-any.whl",
    "httpcore": "httpcore-*-py3-none-any.whl",
    "h11": "h11-*-py3-none-any.whl",
    "requests": "requests-*-py3-none-any.whl",
    "urllib3": "urllib3-*-py3-none-any.whl",
    "idna": "idna-*-py3-none-any.whl",
    "charset_normalizer": "charset_normalizer-*-py3-none-any.whl",
    "certifi": "certifi-*-py3-none-any.whl",
#    "tomlkit": "tomlkit-*-py3-none-any.whl",
#    "markdown": "markdown-*-py3-none-any.whl"
}

def strict_manifest_preflight():
    app_root = Path(__file__).resolve().parent
    bootstrap_cache_dir = Path.home() / "Documents" / "wheels"
    target_user_packages = Path.home() / "Documents" / "site_packages"
    
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
            cached_wheels = list(bootstrap_cache_dir.glob(pattern)) if bootstrap_cache_dir.exists() else []
            
            if cached_wheels:
                # We found a matching wheel file in the installer cache bundle!
                chosen_wheel = cached_wheels[0]
                print(f"  [Found Cache] Using bundled archive to heal '{missing_mod}':\n                -> {chosen_wheel.name}")
                wheels_to_unpack.append(chosen_wheel)
            else:
                # CRITICAL: The wheel file isn't even in the project source tree!
                if not download_instruction_triggered:
                    print("\n!!! BUILD ERROR: MISSING ASSETS DETECTED !!!")
                    print("You need to download the following pure-Python wheels from PyPI")
                    print("and place them inside the 'wheels' folder:\n")
                    download_instruction_triggered = True
                
                print(f"  --> DOWNLOAD REQUIRED: {pattern.replace('*', '[version]')}")

    # 3. Execution Phase: If we have the wheels, gently unpack only the missing targets
    if wheels_to_unpack:
        print(f"\n[Bootstrap] Unpacking {len(wheels_to_unpack)} required modules to user_packages...")
        for wheel_path in wheels_to_unpack:
            try:
                print(f"  -> Unzipping: {wheel_path.name}")
                with zipfile.ZipFile(wheel_path, 'r') as zip_ref:
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

def resolve_and_install_everything(package_spec, target_user_packages):
    from unearth import PackageFinder
    from unearth.resolvelib.providers import PyPIProvider
    from resolvelib import Resolver
    
    # 1. Set up the PyPI link hunter
    finder = PackageFinder()
    
    # 2. Use unearth's built-in bridge to speak to resolvelib
    provider = PyPIProvider(finder, wheel_cache=None)
    
    # 3. Hand the ruleset over to the resolvelib brain
    resolver = Resolver(provider)
    
    print(f"[Resolver] Building complete dependency map for: {package_spec}")
    try:
        # This single step recursively crawls PyPI to calculate every required sub-package
        result = resolver.resolve([package_spec])
        
        # 4. Extract the resolved download links and install them sequentially
        from installer import PackageDistribution
        from installer.sources import WheelFile
        import requests, io
        
        for name, candidate in result.mapping.items():
            link = candidate.link
            print(f"[Resolver] Fulfilling tree requirement: {name} via {link.filename}")
            
            # Fetch and install via your existing pipeline
            # (Using your SchemeDictionaryDestination pointing to user_packages)
            ...
            
    except Exception as e:
        print(f"Dependency resolution collapsed: {e}")

# Use the modern native TOML parser
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # Fallback for older environments

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
            compiled_items.append({
                "title": item.stem,  # Just the filename as the title
                "subtitle": "Standalone Python script.",
                "icon_path": None,   # Uses default fallback icon
                "entry_point": item,
                "folder_root": item.parent,
                "dependencies": []  # Toy scripts have no extra dependencies declared
            })

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
                    
                    compiled_items.append({
                        "title": display_name,
                        "subtitle": desc,
                        "icon_path": icon_path,
                        "entry_point": entry_point,
                        "folder_root": folder_root,
                        "dependencies": dependencies  # Pass the array forward
                    })
                except Exception as e:
                    print(f"Skipping malformed project folder {item.name}: {e}")
                    
    return compiled_items
    
from rubicon.objc import ObjCClass
    
def exit_to_springboard(self):
    """
    Instantly minimizes the active application frame and returns the 
    user smoothly back to the iOS Springboard home screen canvas.
    """
    
    try:
        # 2. Access the native UIKit application instance wrapper
        UIApplication = ObjCClass('UIApplication')
        shared_app = UIApplication.sharedApplication
        
        # 3. Direct the system framework to cleanly minimize the active app
        shared_app.suspend()
        
    except Exception as e:
        # Fallback safety if the bridge layer acts up
        print(f"Objective-C Suspend Failed: {e}")

import toga
from toga.style import Pack

class LauncherApp(toga.App):
    def startup(self):
        self.main_window = toga.MainWindow(title="Launcher")
        self.prototype_dir = Path.home() / "Documents"
        self.bootstrapped = strict_manifest_preflight()
        self.log_box = self.create_log_box()
        self.menu_box = self.create_menu_box()
        self.reload_menu()
        self.load_launcher_menu()
        self.main_window.show()

    def create_log_box(self):
        log_box = toga.Column()
        self.log_text = toga.MultilineTextInput(readonly=True, style=Pack(flex=1))
        scroll_box = toga.ScrollContainer(horizontal=False, content=self.log_text, style=Pack(flex=1))
        log_box.add(scroll_box)
        bottom_bar = toga.Row(style=Pack(margin=(10,), text_align="center"))
        bottom_bar.add(toga.Button("< Back", on_press=self.load_launcher_menu))
        bottom_bar.add(toga.Box(style=Pack(flex=1)))
        bottom_bar.add(toga.Button("Clear", on_press=self.clear_logs))
        log_box.add(bottom_bar)
        return log_box
        
    def create_menu_box(self):
        main_layout = toga.Column()
        
        # 3. Initialize the DetailedList widget
        self.detailed_list = toga.DetailedList(
            on_refresh=self.reload_menu,
            on_select=self.handle_row_selection,
            style=Pack(flex=1)
        )
        
        # Add a refresh button layout at the bottom
        bottom_bar = toga.Row(style=Pack(margin=(10,), text_align="center"))
        bottom_bar.add(toga.Button("Exit", on_press=exit_to_springboard))
        bottom_bar.add(toga.Box(style=Pack(flex=1)))
        bottom_bar.add(toga.Button("Logs", on_press=self.show_logs))
        
        if not self.bootstrapped:
            main_layout.add(toga.Label("Downloads Required!", style=Pack(color="red")))

        main_layout.add(self.detailed_list)
        main_layout.add(bottom_bar)
        
        return main_layout
    
    def show_logs(self, widget=None):
        self.log_text.value = Path("~/Documents/app_runtime.log").expanduser().read_text()
        self.main_window.content = self.log_box

    def clear_logs(self):
        pass

    def reload_menu(self, widget=None):
        # 1. Gather all of our TOML configuration profiles
        self.prototypes_data = scan_all_prototypes(self.prototype_dir)
        
        # 2. Format the records specifically for Toga's DetailedList expectations
        list_items = []
        for proto in self.prototypes_data:
            # Safely build a toga.Image if an icon path was specified and exists
            row_icon = None
            if proto["icon_path"] and proto["icon_path"].exists():
                row_icon = toga.Image(proto["icon_path"])
                
            list_items.append({
                "title": proto["title"],
                "subtitle": proto["subtitle"],
                "icon": row_icon,
                # Toga ignores these custom keys for rendering, but holds onto them for callbacks!
                "entry_point": proto["entry_point"],
                "folder_root": proto["folder_root"],
                "dependencies": proto["dependencies"]
            })
        
        self.detailed_list.data = list_items

    def load_launcher_menu(self, widget=None):        
        self.main_window.content = self.menu_box

    def handle_row_selection(self, widget):
        """Triggered automatically when an iOS row is tapped."""
        import importlib.util

        # Grab the currently selected row data dictionary
        selected_row = widget.selection
        if not selected_row:
            return

        # 1. Read the parsed dependency requirements array
        required_packages = getattr(selected_row, "dependencies", [])
        
        target_user_packages = Path.home() / "Documents" / "site_packages"
        
        # 2. Check and satisfy dependencies
        if required_packages:
            pip = get_pip()
            pip(required_packages, target_user_packages)
        
        # 3. Proceed to mount the folder root and load the module
        import sys
        folder_path = str(selected_row.folder_root)
        if folder_path not in sys.path:
            sys.path.insert(0, folder_path)
        print(f"import path: {sys.path}") 
            
        # Clear out status title alterations and execute
        self.main_window.title = selected_row.title
            
        print(f"Launching {selected_row.title} from path: {selected_row.entry_point}")
        selected_file_path = Path(selected_row.entry_point)

        try:
            # Dynamically load the python module from an arbitrary path
            module_name = selected_file_path.parent.name
            spec = importlib.util.spec_from_file_location(module_name, selected_file_path, submodule_search_locations=(selected_file_path.parent,))
            module = importlib.util.module_from_spec(spec)
            
            # Execute the module code so classes are defined
            spec.loader.exec_module(module)
            
            # Instantiate the prototype class. 
            # Convicting to the design, it must look for a class named 'Prototype'
            if hasattr(module, "Prototype"):
                # Pass the host app instance AND the done callback function straight down
                self.current_prototype = module.Prototype(host_app=self, on_done=self.handle_prototype_done)
                
                # Update window context and inject the prototype layout
                self.main_window.title = getattr(self.current_prototype, "title", "Running Prototype")
                self.main_window.content = self.current_prototype.get_content()
            else:
                self.main_window.info_dialog("Error", f"No 'Prototype' class found in {selected_file_path.name}")
                
        except Exception as e:
            self.main_window.error_dialog("Load Failure", f"Failed to execute script:\n{str(e)}")

    def handle_prototype_done(self):
        """The absolute explicit callback contract to escape a prototype."""
        print("[Launcher] Prototype declared execution complete. Returning to menu.")
        if self.current_prototype:
            # Explicitly clear out references to help Python garbage collect the dynamic module
            self.current_prototype = None 
        
        # Smoothly draw the picker back over the screen
        self.load_launcher_menu()

        # Run any cleanup on the previous layout if needed
        # (You could track self.current_prototype to trigger on_deactivate)

def main():
    return LauncherApp()
