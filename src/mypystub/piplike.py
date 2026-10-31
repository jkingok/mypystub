import asyncio
import importlib.metadata
import platform
import re
import shutil
import sys
import tempfile
import zipfile
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio
import httpx2
import resolvelib
from installer import install
from installer.destinations import SchemeDictionaryDestination
from installer.sources import WheelFile
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import Version
from unearth import PackageFinder, TargetPython
from unearth.link import Link


class DependencyError(Exception):
    """Raised when dependency resolution, downloading, or unpacking fails."""


@dataclass(frozen=True)
class Candidate:
    name: str
    version: Version
    link: Link | None = None
    is_system: bool = False
    # Use frozenset for immutability so dataclass remains hashable
    requested_extras: frozenset[str] = frozenset()

    def __post_init__(self):
        object.__setattr__(self, "name", canonicalize_name(self.name))

    def __str__(self) -> str:
        source = "system" if self.is_system else "pypi"
        extras_str = (
            f"[{','.join(sorted(self.requested_extras))}]"
            if self.requested_extras
            else ""
        )
        return f"{self.name}{extras_str} {self.version} ({source})"


class PyPIWheelProvider(resolvelib.AbstractProvider):
    def __init__(
        self,
        finder: PackageFinder,
        cache_dir: Path,
        system_packages: dict[str, Version],
        http_client: httpx2.Client,
        package_substitutions: dict[str, str] | None = None,
        use_system: bool = True,
        max_candidates: int = 5,
    ):
        self.finder = finder
        self.cache_dir = cache_dir
        self.system_packages = {
            canonicalize_name(k): v for k, v in system_packages.items()
        }
        self.http_client = http_client
        self.use_system = use_system
        self.max_candidates = max_candidates
        self.package_substitutions = {
            canonicalize_name(k): canonicalize_name(v)
            for k, v in (package_substitutions or {"pyyaml": "pyyaml-pure"}).items()
        }
        self._dep_cache: dict[Candidate, list[Requirement]] = {}

    def identify(self, requirement_or_candidate) -> str:
        raw_name = canonicalize_name(requirement_or_candidate.name)
        return self.package_substitutions.get(raw_name, raw_name)

    def get_preference(
        self, identifier, resolutions, candidates, information, backtrack_causes
    ):
        return sum(1 for _ in information[identifier])

    def find_matches(
        self, identifier, requirements, incompatibilities
    ) -> list[Candidate]:
        canon_id = canonicalize_name(identifier)
        req_specs = [
            r for r in requirements.get(identifier, []) if isinstance(r, Requirement)
        ]

        # resolvelib maps identifier -> candidates already ruled out (backtracking)
        excluded = set(incompatibilities.get(identifier, ()))

        # Collect explicitly requested extras as a frozenset
        active_extras: frozenset[str] = frozenset(
            extra for req in req_specs if req.extras for extra in req.extras
        )

        candidates: list[Candidate] = []

        # 1. System Candidate Lookup
        if self.use_system and canon_id in self.system_packages:
            sys_cand = Candidate(
                name=canon_id,
                version=self.system_packages[canon_id],
                is_system=True,
                requested_extras=active_extras,
            )
            if sys_cand not in excluded and all(
                self.is_satisfied_by(req, sys_cand) for req in req_specs
            ):
                candidates.append(sys_cand)

        # 2. PyPI Candidate Lookup
        matches = self.finder.find_matches(canon_id)
        for match in matches:
            if not match.version:
                continue

            filename = match.link.filename.lower()

            if filename.endswith(".whl"):
                # Strip '.whl' and get the platform tag (the final hyphen-separated segment)
                platform_tag = filename[:-4].split("-")[-1]

                # Reject only if the actual platform tag targets real iOS hardware
                if "iphoneos" in platform_tag:
                    continue

            cand = Candidate(
                name=canonicalize_name(match.name),
                version=Version(match.version),
                link=match.link,
                is_system=False,
                requested_extras=active_extras,
            )
            if cand not in excluded and all(
                self.is_satisfied_by(req, cand) for req in req_specs
            ):
                candidates.append(cand)

        sorted_candidates = sorted(
            candidates,
            key=lambda c: (c.is_system, c.version),
            reverse=True,
        )
        return sorted_candidates[: self.max_candidates]

    def is_satisfied_by(self, requirement: Requirement, candidate: Candidate) -> bool:
        return (canonicalize_name(requirement.name) == candidate.name) and not (
            requirement.specifier
            and not requirement.specifier.contains(candidate.version, prereleases=True)
        )

    def get_dependencies(self, candidate: Candidate) -> list[Requirement]:
        if candidate in self._dep_cache:
            return self._dep_cache[candidate]

        if candidate.is_system:
            deps = self._get_system_dependencies(candidate)
        else:
            metadata_text = self._fetch_candidate_metadata(candidate)
            deps = self._parse_metadata_requirements(
                metadata_text, candidate.requested_extras
            )

        self._dep_cache[candidate] = deps
        return deps

    def _parse_metadata_requirements(
        self, metadata_content: str, active_extras: frozenset[str]
    ) -> list[Requirement]:
        reqs: list[Requirement] = []

        for line in metadata_content.splitlines():
            if not line.startswith("Requires-Dist:"):
                continue

            raw_req = line.split("Requires-Dist:", 1)[1].strip()
            req = Requirement(raw_req)

            # Conservative Extra Evaluation Guard:
            if req.marker:
                # 1. Evaluate default environment without any active extras
                is_base_dep = req.marker.evaluate({"extra": ""})

                # 2. If it's not a base dependency, check if it matches an explicitly requested extra
                is_requested_extra = any(
                    req.marker.evaluate({"extra": extra}) for extra in active_extras
                )

                # Skip dependency if it requires an unrequested extra (e.g. extra == 'testing')
                if not (is_base_dep or is_requested_extra):
                    continue

            # Apply package substitutions (e.g., pyyaml -> pyyaml-pure)
            canon_req_name = canonicalize_name(req.name)
            if canon_req_name in self.package_substitutions:
                subbed_name = self.package_substitutions[canon_req_name]
                spec_str = str(req.specifier) if req.specifier else ""
                marker_str = f" ; {req.marker}" if req.marker else ""
                req = Requirement(f"{subbed_name}{spec_str}{marker_str}")

            reqs.append(req)

        return reqs

    def _get_system_dependencies(self, candidate: Candidate) -> list[Requirement]:
        reqs: list[Requirement] = []
        try:
            dist = importlib.metadata.distribution(candidate.name)
            if dist.requires:
                # Re-use metadata parser logic for consistency
                raw_metadata = "\n".join(f"Requires-Dist: {r}" for r in dist.requires)
                return self._parse_metadata_requirements(
                    raw_metadata, candidate.requested_extras
                )
        except importlib.metadata.PackageNotFoundError:
            pass
        return reqs

    def _fetch_candidate_metadata(self, candidate: Candidate) -> str:
        if not candidate.link:
            return ""
        metadata_url = f"{candidate.link.url}.metadata"
        try:
            resp = self.http_client.get(metadata_url, follow_redirects=True)
            if resp.status_code == 200:
                return resp.text
        except httpx2.HTTPError:
            pass
        return ""


class ResolutionProgressReporter(resolvelib.BaseReporter):
    """Provides visibility into resolution progress instead of remaining silent."""

    def __init__(self, on_progress: Callable[[str], None] | None = None) -> None:
        """Optionally forward short progress messages to `on_progress`."""
        self.on_progress = on_progress

    def starting(self) -> None:
        print("[Resolver] Starting dependency graph resolution...")

    def starting_round(self, index: int) -> None:
        print(f"[Resolver] Round {index}...")

    def pinning(self, candidate) -> None:
        print(f"[Resolver] -> Pinned candidate: {candidate}")
        if self.on_progress:
            self.on_progress(f"Resolved {candidate.name} {candidate.version}")

    def rejecting_candidate(self, criterion, candidate) -> None:
        print(f"[Resolver] -> Backtracking: Rejected {candidate}")


# Helper Functions


async def download_wheel_async(
    client: httpx2.AsyncClient, url: str, target_path: Path
) -> None:
    """Asynchronously streams a wheel file to disk using HTTPX2."""
    try:
        async with client.stream("GET", url, follow_redirects=True) as response:
            response.raise_for_status()
            async with await anyio.open_file(target_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    await f.write(chunk)
    except (httpx2.HTTPError, OSError) as exc:
        raise DependencyError(f"Async download failed for {url}: {exc}") from exc


def unpack_wheel(wheel_path: Path, target_site_packages: Path) -> None:
    destination = SchemeDictionaryDestination(
        scheme_dict={
            "purelib": str(target_site_packages),
            "platlib": str(target_site_packages),
            "headers": str(target_site_packages / "headers"),
            "scripts": str(target_site_packages / "bin"),
            "data": str(target_site_packages / "data"),
        },
        interpreter=sys.executable,
        script_kind="posix" if sys.platform != "win32" else "win",
    )
    with WheelFile.open(wheel_path) as source:
        install(source=source, destination=destination, additional_metadata={})


# Main Async Entry Point


async def resolve_and_install_async(
    requirements: list[str],
    target_dir: Path,
    index_urls: list[str] | None = None,
    cache_dir: Path | None = None,
    clean: bool = False,
    force_reinstall: bool = False,
    use_system: bool = True,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """
    Async dependency resolver and installer compatible with Toga / asyncio event loops.

    Blocking work (resolution, metadata scans, unpacking) runs in worker threads.
    `on_progress` receives short status messages, always on the event loop thread,
    so it may update widgets directly.
    """
    loop = asyncio.get_running_loop()

    def progress(message: str) -> None:
        print(f"[Progress] {message}")
        if on_progress:
            on_progress(message)

    def progress_threadsafe(message: str) -> None:
        loop.call_soon_threadsafe(progress, message)

    is_temp_cache = False

    progress("Resolving dependencies")
    if cache_dir is None:
        try:
            cache_dir = Path(
                await asyncio.to_thread(tempfile.mkdtemp, prefix="wheel_cache_")
            )
            is_temp_cache = True
            print(f"Temporary wheel cache is {cache_dir}")
        except OSError as exc:
            raise DependencyError(
                f"Failed to create temporary cache directory: {exc}"
            ) from exc
    else:
        cache_dir.mkdir(parents=True, exist_ok=True)

    # Default index list includes PyPI and BeeWare PyPI
    indexes = index_urls or [
        "https://pypi.org/simple/",
        # "https://pypi.anaconda.org/beeware/simple/", # no point using while binaries are unsigned
    ]

    try:
        if clean and target_dir.exists():
            print(f"will clean {target_dir}")
            await asyncio.to_thread(shutil.rmtree, target_dir)

        target_dir.mkdir(parents=True, exist_ok=True)

        # Offload resolution phase to thread so unearth/resolvelib don't freeze Toga UI
        def _sync_resolve_pass():
            raw_system_pkgs = get_package_inventory(None) if use_system else {}
            system_packages = {
                name: Version(ver) for name, ver in raw_system_pkgs.items()
            }

            # 1. Initialize finder with target index and constraints
            finder = PackageFinder(
                index_urls=indexes,
                target_python=TargetPython(),
                only_binary={":all:"},
            )

            # 2. Enforce strict timeout on unearth's internal session to prevent infinite hanging
            # finder.session.timeout = 10.0

            # 3. Perform lightweight resolution using HTTPX2 and PEP 658 metadata
            with httpx2.Client(timeout=10.0) as sync_http:
                provider = PyPIWheelProvider(
                    finder=finder,
                    cache_dir=cache_dir,
                    system_packages=system_packages,
                    http_client=sync_http,
                    use_system=use_system,
                    max_candidates=5,  # Limit to top 5 candidates per package
                )

                # Use custom progress reporter to track execution in console/UI
                reporter = ResolutionProgressReporter(progress_threadsafe)
                resolver = resolvelib.Resolver(provider, reporter)

                parsed_reqs = [Requirement(r) for r in requirements]
                return resolver.resolve(parsed_reqs)

        try:
            resolution = await asyncio.to_thread(_sync_resolve_pass)
        except resolvelib.ResolutionError as exc:
            raise DependencyError(f"Dependency resolution failed: {exc}") from exc

        # Async Download & Install Phase
        async with httpx2.AsyncClient(timeout=30.0) as async_http:
            for candidate in resolution.mapping.values():
                if candidate.is_system:
                    continue

                installed = await asyncio.to_thread(
                    get_installed_distribution, target_dir, candidate.name
                )
                wheel_path = cache_dir / candidate.link.filename

                if installed:
                    installed_version = Version(installed.version)
                    if installed_version == candidate.version and not force_reinstall:
                        continue
                    else:
                        print(
                            f"upgrading {candidate.name} from {installed_version} to {candidate.version}"
                        )
                        progress(f"Removing {candidate.name} {installed_version}")
                        await asyncio.to_thread(
                            remove_installed_package, target_dir, candidate.name
                        )

                # Download wheel asynchronously if not cached
                if not wheel_path.exists():
                    print(f"downloading {candidate.link}")
                    progress(f"Downloading {candidate.name} {candidate.version}")
                    await download_wheel_async(
                        async_http, candidate.link.url, wheel_path
                    )

                # Unpack wheel on a worker thread
                progress(f"Installing {candidate.name} {candidate.version}")
                try:
                    await asyncio.to_thread(unpack_wheel, wheel_path, target_dir)
                except (zipfile.BadZipFile, OSError) as exc:
                    raise DependencyError(
                        f"Failed to unpack {wheel_path.name}: {exc}"
                    ) from exc
        print("successfully met all requirements")
        progress("Dependencies ready")
    finally:
        if is_temp_cache and cache_dir.exists():
            print("removing temporary wheel cache")
            await asyncio.to_thread(shutil.rmtree, cache_dir, True)


# Use the modern native TOML parser
import tomllib  # Fallback for older environments

PEP723_BLOCK = re.compile(
    r"(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$"
)

# Loose scripts that are part of the launcher itself, not prototypes
RESERVED_SCRIPTS = frozenset({"patch_app.py", "__init__.py"})

# Folders that never hold prototypes
SKIPPED_FOLDERS = frozenset({"__pycache__", "site-packages", "site_packages"})


def iter_script_metadata(script: str) -> Iterator[tuple[str, str]]:
    """Yield ``(type, toml_text)`` for each PEP 723 metadata block in a script."""
    for match in PEP723_BLOCK.finditer(script):
        yield (
            match.group("type"),
            "".join(
                line[2:] if line.startswith("# ") else line[1:]
                for line in match.group("content").splitlines(keepends=True)
            ),
        )


def scan_script(item: Path) -> dict[str, Any] | None:
    """Describe a loose ``.py`` prototype, or return None if it cannot run here.

    Dependencies come from the PEP 723 ``script`` block. A script whose
    ``requires-python`` excludes the running interpreter is skipped.
    """
    dependencies: list[str] = []
    for kind, text in iter_script_metadata(item.read_text(encoding="utf-8")):
        if kind != "script":
            continue
        config = tomllib.loads(text)
        dependencies += config.get("dependencies", [])
        if requires_python := config.get("requires-python"):
            current = platform.python_version()
            if Version(current) not in SpecifierSet(requires_python):
                print(
                    f"Skipping {item.name} needs Python {requires_python} "
                    f"not {current}"
                )
                return None
        # TODO we can implement our custom tool in this
        # same metadata to capture description, etc

    return {
        "title": item.stem,  # Just the filename as the title
        "subtitle": "Standalone Python script.",
        "icon_path": None,  # Uses default fallback icon
        "entry_point": item,
        "folder_root": item.parent,
        "dependencies": dependencies,
    }


def scan_project(item: Path) -> dict[str, Any]:
    """Describe a project folder from its ``pyproject.toml``."""
    with open(item / "pyproject.toml", "rb") as f:
        toml_data = tomllib.load(f)

    # Read standard PEP 621 table
    project_meta = toml_data.get("project", {})
    name = project_meta.get("name", item.name)
    desc = project_meta.get("description", "Project directory module.")

    # Read tool overrides
    tool_meta = toml_data.get("tool", {}).get("stub_launcher", {})
    icon_relative = tool_meta.get("icon")

    return {
        "title": tool_meta.get("display_name", name),
        "subtitle": desc,
        "icon_path": item / icon_relative if icon_relative else None,
        # Target launch file path relative to its home folder
        "entry_point": item / tool_meta.get("entry_point", "main.py"),
        "folder_root": item / tool_meta.get("import_path", "src"),
        # PEP 621 dependencies list (default to empty list if missing)
        "dependencies": project_meta.get("dependencies", []),
    }


def scan_folder(item: Path) -> dict[str, Any]:
    """Describe a plain folder that the launcher can navigate into."""
    return {
        "title": item.name,
        "subtitle": "Folder",
        "icon_path": None,
        "folder": item,
        "dependencies": [],
    }


def scan_all_prototypes(base_dir: Path) -> Iterable[Mapping[str, Any]]:
    """List the prototypes and sub-folders directly inside ``base_dir``.

    Folders come first, then scripts and project folders, each sorted by name.
    Folders with a ``pyproject.toml`` are runnable projects; other folders are
    returned with a ``folder`` key so the launcher can drill into them.
    """
    folders: list[Mapping[str, Any]] = []
    prototypes: list[Mapping[str, Any]] = []
    print(f"Scanning for launcher prototypes in: {base_dir}")

    if not base_dir.is_dir():
        return prototypes

    for item in sorted(base_dir.iterdir(), key=lambda x: x.name.lower()):
        # Skip hidden files/folders (like .DS_Store or system bits)
        if item.name.startswith("."):
            continue

        try:
            # --- CASE A: The "Toy Script" (Loose .py file) ---
            if item.is_file() and item.suffix == ".py":
                # Don't accidentally auto-load your main launcher scripts
                if item.name not in RESERVED_SCRIPTS and (entry := scan_script(item)):
                    prototypes.append(entry)

            # --- CASE B: The "Full Project" (Folder with pyproject.toml) ---
            elif item.is_dir() and (item / "pyproject.toml").exists():
                prototypes.append(scan_project(item))

            # --- CASE C: A plain folder to navigate into ---
            elif item.is_dir() and item.name not in SKIPPED_FOLDERS:
                folders.append(scan_folder(item))
        except (OSError, ValueError) as e:
            # ValueError covers TOMLDecodeError, bad specifiers and bad versions
            print(f"Skipping malformed prototype {item.name}: {e}")

    return folders + prototypes


def relative_folder(base_dir: Path, folder: Path) -> Path:
    """Return ``folder`` relative to ``base_dir``, refusing to leave ``base_dir``.

    Used for launcher navigation so ``..`` and symlinks cannot escape the
    prototype root.
    """
    base = base_dir.resolve()
    target = folder.resolve()
    if not target.is_relative_to(base):
        return Path()
    return target.relative_to(base)


# Package Inventory Utility


def get_package_inventory(target_path: Path | None = None) -> dict[str, str]:
    """
    Returns a dictionary of installed package names and versions.

    :param target_path: Directory path to inspect (e.g. custom_site_packages).
                        If None, inspects the current system Python environment.
    """
    packages: dict[str, str] = {}

    if target_path is None:
        # Standard system site-packages search via default sys.path
        for dist in importlib.metadata.distributions():
            name = canonicalize_name(dist.metadata["Name"])
            packages[name] = dist.version
    else:
        resolved_path = target_path.resolve()
        if resolved_path.exists():
            for dist in importlib.metadata.distributions(path=[str(resolved_path)]):
                name = canonicalize_name(dist.metadata["Name"])
                packages[name] = dist.version

    return packages


# Maintenance Helpers


def get_installed_distribution(
    target_site_packages: Path, package_name: str
) -> importlib.metadata.Distribution | None:
    canon_name = canonicalize_name(package_name)
    if not target_site_packages.exists():
        return None

    for dist in importlib.metadata.distributions(path=[str(target_site_packages)]):
        if canonicalize_name(dist.metadata["Name"]) == canon_name:
            return dist
    return None


def remove_installed_package(target_site_packages: Path, package_name: str) -> None:
    dist = get_installed_distribution(target_site_packages, package_name)
    if not dist:
        return

    if dist.files:
        for relative_path in dist.files:
            file_path = (target_site_packages / relative_path).resolve()
            if (
                file_path.is_relative_to(target_site_packages.resolve())
                and file_path.exists()
            ):
                if file_path.is_file() or file_path.is_symlink():
                    file_path.unlink()

                parent = file_path.parent
                while (
                    parent != target_site_packages
                    and parent.exists()
                    and not any(parent.iterdir())
                ):
                    parent.rmdir()
                    parent = parent.parent

    dist_info_path = getattr(dist, "_path", None)
    if dist_info_path and Path(dist_info_path).exists():
        shutil.rmtree(dist_info_path, ignore_errors=True)
