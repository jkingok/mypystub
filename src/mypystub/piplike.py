import ast
import asyncio
import importlib
import importlib.metadata
import platform
import re
import shutil
import sys
import tempfile
import zipfile
from collections import deque
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


ALIAS_KINDS = ("bundled", "substitute")
ALIAS_WHEN = ("no_wheel", "always")
ALIAS_SPECIFIER = ("drop", "keep")


@dataclass(frozen=True)
class Alias:
    """A requirement that is really satisfied by another distribution (#79).

    :param kind: ``"bundled"``: satisfied by a distribution the app bundles, so
        nothing is installed (``toga`` is provided by ``toga-core``).
        ``"substitute"``: install `target` instead, typically a pure-Python
        replacement for a package with no wheel for this platform.
    :param target: The distribution that satisfies the requirement.
    :param when: For substitutes: ``"no_wheel"`` (the default) tries the
        original first and only substitutes when it has no compatible wheel;
        ``"always"`` always substitutes.
    :param specifier: For substitutes: ``"drop"`` (the default) ignores the
        requirement's version specifier, since the two projects number their
        versions differently; ``"keep"`` applies it to the substitute.
    """

    kind: str
    target: str
    when: str = "no_wheel"
    specifier: str = "drop"


# Built-in aliases. Each substitute is a verified drop-in: same import name,
# compatible API, and a pure-Python (py3-none-any) wheel.
ALIASES = {
    # The toga meta-package isn't bundled, but toga-core and the backend are
    "toga": Alias("bundled", "toga-core"),
    # PyYAML's wheels are compiled and none are built for iOS; pyyaml-pure
    # provides the same `yaml` package (safe_load, dump, YAMLError, loaders)
    "pyyaml": Alias("substitute", "pyyaml-pure"),
}


def parse_aliases(table: Mapping[str, Any]) -> dict[str, Alias]:
    """Read an alias table, as written in launcher.toml or [tool.stub_launcher].

    Each entry is ``name = { kind = "...", target = "...", when = "...",
    specifier = "..." }``. Raises ValueError for anything malformed, so typos
    don't silently change what gets installed.
    """
    aliases: dict[str, Alias] = {}
    for name, entry in table.items():
        if not isinstance(entry, Mapping) or "target" not in entry:
            raise ValueError(f"alias {name!r} needs a table with a target")
        alias = Alias(
            kind=str(entry.get("kind", "substitute")),
            target=canonicalize_name(str(entry["target"])),
            when=str(entry.get("when", "no_wheel")),
            specifier=str(entry.get("specifier", "drop")),
        )
        if (
            alias.kind not in ALIAS_KINDS
            or alias.when not in ALIAS_WHEN
            or alias.specifier not in ALIAS_SPECIFIER
        ):
            raise ValueError(f"alias {name!r} has an unknown kind, when or specifier")
        aliases[canonicalize_name(name)] = alias
    return aliases


@dataclass(frozen=True)
class Candidate:
    name: str
    version: Version
    link: Link | None = None
    is_system: bool = False
    # Already unpacked into the target site-packages by an earlier run
    is_installed: bool = False
    # Use frozenset for immutability so dataclass remains hashable
    requested_extras: frozenset[str] = frozenset()
    # The requirement name this candidate satisfies; differs from `name` when an
    # alias substitutes another distribution (pyyaml satisfied by pyyaml-pure)
    identifier: str = ""

    def __post_init__(self):
        object.__setattr__(self, "name", canonicalize_name(self.name))
        object.__setattr__(
            self, "identifier", canonicalize_name(self.identifier or self.name)
        )

    def __str__(self) -> str:
        source = (
            "system" if self.is_system else "installed" if self.is_installed else "pypi"
        )
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
        aliases: Mapping[str, Alias] | None = None,
        use_system: bool = True,
        max_candidates: int = 5,
        installed_packages: dict[str, Version] | None = None,
        target_dir: Path | None = None,
    ):
        """Resolve against bundled, then installed, then PyPI packages.

        `system_packages` are bundled with the app and always win: PyPI is never
        consulted for them, so nothing can shadow the app's own copies.
        `installed_packages` were unpacked into `target_dir` by earlier runs and
        are reused when they satisfy the requirement. PyPI is only queried
        lazily, when no local candidate fits, so satisfied scripts run offline.
        """
        self.finder = finder
        self.cache_dir = cache_dir
        self.system_packages: dict[str, Version] = {
            canonicalize_name(k): v for k, v in system_packages.items()
        }
        self.aliases: dict[str, Alias] = {
            canonicalize_name(k): v for k, v in {**ALIASES, **(aliases or {})}.items()
        }
        for name, alias in self.aliases.items():
            source = canonicalize_name(alias.target)
            if (
                alias.kind == "bundled"
                and name not in self.system_packages
                and source in self.system_packages
            ):
                self.system_packages[name] = self.system_packages[source]
        self.installed_packages: dict[str, Version] = {
            canonicalize_name(k): v for k, v in (installed_packages or {}).items()
        }
        self.target_dir = target_dir
        self._warned: set[str] = set()
        self.http_client = http_client
        self.use_system = use_system
        self.max_candidates = max_candidates
        self._dep_cache: dict[Candidate, list[Requirement]] = {}

    def identify(self, requirement_or_candidate) -> str:
        if isinstance(requirement_or_candidate, Candidate):
            return requirement_or_candidate.identifier
        return canonicalize_name(requirement_or_candidate.name)

    def substitute_for(self, identifier: str) -> Alias | None:
        """The substitute alias for `identifier`, if there is one."""
        alias = self.aliases.get(identifier)
        return alias if alias and alias.kind == "substitute" else None

    def get_preference(
        self, identifier, resolutions, candidates, information, backtrack_causes
    ):
        return sum(1 for _ in information[identifier])

    def find_matches(
        self, identifier, requirements, incompatibilities
    ) -> list[Candidate] | Callable[[], Iterator[Candidate]]:
        canon_id = canonicalize_name(identifier)
        req_specs = [
            r for r in requirements.get(identifier, []) if isinstance(r, Requirement)
        ]

        # resolvelib maps identifier -> candidates already ruled out (backtracking)
        excluded: set[Candidate] = set(incompatibilities.get(identifier, ()))

        # Collect explicitly requested extras as a frozenset
        active_extras: frozenset[str] = frozenset(
            extra for req in req_specs if req.extras for extra in req.extras
        )

        # 1. Bundled packages always win, even against a conflicting specifier.
        # A second copy in site_packages would shadow the app's own, which is
        # already imported, and mix versions. PyPI is never consulted for them.
        if self.use_system and canon_id in self.system_packages:
            sys_cand = Candidate(
                name=canon_id,
                version=self.system_packages[canon_id],
                is_system=True,
                requested_extras=active_extras,
            )
            for req in req_specs:
                self._warn_if_bundled_mismatch(req, sys_cand)
            return [] if sys_cand in excluded else [sys_cand]

        # 2. A copy installed by an earlier run, if it fits: the package itself,
        # or its substitute (so an installed pyyaml-pure satisfies pyyaml offline)
        substitute = self.substitute_for(canon_id)
        local: list[Candidate] = []
        names = [canon_id] + ([substitute.target] if substitute else [])
        for name in names:
            if name not in self.installed_packages:
                continue
            installed = Candidate(
                name=name,
                version=self.installed_packages[name],
                is_installed=True,
                requested_extras=active_extras,
                identifier=canon_id,
            )
            if installed not in excluded and all(
                self.is_satisfied_by(req, installed) for req in req_specs
            ):
                local.append(installed)

        # 3. PyPI, only if resolvelib iterates past the local candidates. With a
        # substitute alias: the original first (unless when="always"), and the
        # substitute only if the original has no compatible wheel.
        def candidates() -> Iterator[Candidate]:
            yield from local
            skip = {(c.name, c.version) for c in local}
            found = []
            if not (substitute and substitute.when == "always"):
                found = self._pypi_candidates(
                    canon_id, canon_id, req_specs, excluded, active_extras, skip
                )
                yield from found
            if substitute and not found:
                reason = (
                    "always"
                    if substitute.when == "always"
                    else "no compatible wheel for this platform"
                )
                self._note(
                    f"alias:{canon_id}",
                    f"[Resolver] {canon_id} → {substitute.target} ({reason})",
                )
                yield from self._pypi_candidates(
                    substitute.target,
                    canon_id,
                    req_specs,
                    excluded,
                    active_extras,
                    skip,
                )

        return candidates

    def _note(self, key: str, message: str) -> None:
        """Print `message` once per resolution."""
        if key not in self._warned:
            self._warned.add(key)
            print(message)

    def _pypi_candidates(
        self,
        canon_id: str,
        identifier: str,
        req_specs: list[Requirement],
        excluded: set[Candidate],
        active_extras: frozenset[str],
        skip: set[tuple[str, Version]],
    ) -> list[Candidate]:
        """Index candidates for `canon_id`, satisfying `identifier`, newest first."""
        try:
            matches = self.finder.find_matches(canon_id)
        except Exception as exc:
            # Offline, DNS failure, index error: name the package that needed it
            raise DependencyError(
                f"{canon_id} is not installed and the package index could not be "
                f"reached: {exc}"
            ) from exc

        candidates: list[Candidate] = []
        for match in matches:
            if not match.version:
                continue
            if (canonicalize_name(match.name), Version(match.version)) in skip:
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
                identifier=identifier,
            )
            if cand not in excluded and all(
                self.is_satisfied_by(req, cand) for req in req_specs
            ):
                candidates.append(cand)

        candidates.sort(key=lambda c: c.version, reverse=True)
        return candidates[: self.max_candidates]

    def _warn_if_bundled_mismatch(self, req: Requirement, cand: Candidate) -> None:
        """Log once when a bundled package doesn't meet a script's specifier."""
        if (
            req.specifier
            and not req.specifier.contains(cand.version, prereleases=True)
            and cand.name not in self._warned
        ):
            self._warned.add(cand.name)
            print(
                f"[Resolver] Warning: bundled {cand.name} {cand.version} does not "
                f"satisfy {req}; using the bundled copy"
            )

    def is_satisfied_by(self, requirement: Requirement, candidate: Candidate) -> bool:
        if candidate.is_system:
            # Bundled packages always win (see find_matches)
            if self.identify(requirement) == candidate.name:
                self._warn_if_bundled_mismatch(requirement, candidate)
                return True
            return False
        if self.identify(requirement) != candidate.identifier:
            return False
        if candidate.name != candidate.identifier:
            # A substitute: version numbers belong to a different project
            alias = self.substitute_for(candidate.identifier)
            if alias is None or alias.specifier == "drop":
                if requirement.specifier:
                    self._note(
                        f"spec:{candidate.identifier}",
                        f"[Resolver] {candidate.identifier} → {candidate.name}: "
                        f"ignoring {requirement.specifier}",
                    )
                return True
        return not (
            requirement.specifier
            and not requirement.specifier.contains(candidate.version, prereleases=True)
        )

    def get_dependencies(self, candidate: Candidate) -> list[Requirement]:
        if candidate in self._dep_cache:
            return self._dep_cache[candidate]

        if candidate.is_system:
            deps = self._get_system_dependencies(candidate)
        elif candidate.is_installed:
            deps = self._get_installed_dependencies(candidate)
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

            # Aliases (pyyaml -> pyyaml-pure) are applied per platform in find_matches
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

    def _get_installed_dependencies(self, candidate: Candidate) -> list[Requirement]:
        """Read an installed package's dependencies from its metadata on disk."""
        if self.target_dir is None:
            return []
        dist = get_installed_distribution(self.target_dir, candidate.name)
        if dist is None or not dist.requires:
            return []
        raw_metadata = "\n".join(f"Requires-Dist: {r}" for r in dist.requires)
        return self._parse_metadata_requirements(
            raw_metadata, candidate.requested_extras
        )

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
    aliases: Mapping[str, Alias] | None = None,
) -> None:
    """
    Async dependency resolver and installer compatible with Toga / asyncio event loops.

    Blocking work (resolution, metadata scans, unpacking) runs in worker threads.
    `on_progress` receives short status messages, always on the event loop thread,
    so it may update widgets directly. `aliases` (from launcher.toml or the
    script) are merged over the built-in ALIASES.
    """
    loop = asyncio.get_running_loop()

    def progress(message: str) -> None:
        print(f"[Progress] {message}")
        if on_progress:
            on_progress(message)

    # Messages from worker threads wait here in order. The loop delivers them
    # when it gets round to it, and drain_progress() delivers any still waiting
    # once the worker is done, so none can arrive after a later message.
    pending: deque[str] = deque()

    def drain_progress() -> None:
        while pending:
            try:
                message = pending.popleft()
            except IndexError:  # drained by the other caller meanwhile
                return
            progress(message)

    def progress_threadsafe(message: str) -> None:
        pending.append(message)
        loop.call_soon_threadsafe(drain_progress)

    is_temp_cache = False

    progress("Checking dependencies")
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
            raw_system_pkgs = get_bundled_inventory(target_dir) if use_system else {}
            system_packages = {
                name: Version(ver) for name, ver in raw_system_pkgs.items()
            }
            # Reuse earlier installs unless asked to reinstall
            raw_installed = {} if force_reinstall else get_package_inventory(target_dir)
            installed_packages = {
                name: Version(ver) for name, ver in raw_installed.items()
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
                    installed_packages=installed_packages,
                    target_dir=target_dir,
                    aliases=aliases,
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
        finally:
            drain_progress()  # the resolver's messages come before anything after

        # Async Download & Install Phase
        changed = 0
        async with httpx2.AsyncClient(timeout=30.0) as async_http:
            for candidate in resolution.mapping.values():
                if candidate.is_system or candidate.is_installed:
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
                changed += 1
                progress(f"Installing {candidate.name} {candidate.version}")
                try:
                    await asyncio.to_thread(unpack_wheel, wheel_path, target_dir)
                except (zipfile.BadZipFile, OSError) as exc:
                    raise DependencyError(
                        f"Failed to unpack {wheel_path.name}: {exc}"
                    ) from exc
        if changed:
            # Python may have cached "nothing here" for target_dir while it was
            # missing or empty; forget that so the new packages can be imported
            importlib.invalidate_caches()
        print("successfully met all requirements")
        progress("Dependencies ready" if changed else "Dependencies already satisfied")
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

# Subtitle for a loose script without a module docstring
DEFAULT_SCRIPT_SUBTITLE = "Standalone Python script."

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


def docstring_summary(source: str) -> str | None:
    """Return the first line of a module's docstring, or None if there isn't one.

    Scripts that fail to parse still get listed, so a syntax error returns None
    rather than raising; the error is reported when the script is run.
    """
    try:
        docstring = ast.get_docstring(ast.parse(source))
    except SyntaxError:
        return None
    if not docstring:
        return None
    return docstring.strip().splitlines()[0].strip() or None


def scan_script(item: Path) -> dict[str, Any] | None:
    """Describe a loose ``.py`` prototype, or return None if it cannot run here.

    Dependencies come from the PEP 723 ``script`` block. A script whose
    ``requires-python`` excludes the running interpreter is skipped.

    The same block may hold a ``[tool.stub_launcher]`` table with the keys a
    project folder uses: ``display_name`` (else the file name), ``description``
    (else the first line of the module docstring) and ``icon`` (a path relative
    to the script's folder).
    """
    source = item.read_text(encoding="utf-8")
    dependencies: list[str] = []
    launcher: dict[str, Any] = {}
    for kind, text in iter_script_metadata(source):
        if kind != "script":
            continue
        config = tomllib.loads(text)
        dependencies += config.get("dependencies", [])
        launcher |= config.get("tool", {}).get("stub_launcher", {})
        if requires_python := config.get("requires-python"):
            current = platform.python_version()
            if Version(current) not in SpecifierSet(requires_python):
                print(
                    f"Skipping {item.name} needs Python {requires_python} not {current}"
                )
                return None

    return {
        "title": launcher.get("display_name") or item.stem,
        "subtitle": launcher.get("description")
        or docstring_summary(source)
        or DEFAULT_SCRIPT_SUBTITLE,
        "icon_path": _icon_within(item.parent, launcher.get("icon")),
        "entry_point": item,
        "folder_root": item.parent,
        "dependencies": dependencies,
        "aliases": parse_aliases(launcher.get("aliases", {})),
        "kind": "script",
    }


def _icon_within(folder: Path, relative: str | None) -> Path | None:
    """Resolve an icon path relative to ``folder``, refusing paths outside it."""
    if not relative:
        return None
    icon = folder / relative
    if not icon.resolve().is_relative_to(folder.resolve()):
        print(f"Ignoring icon outside {folder}: {relative}")
        return None
    return icon


@dataclass(frozen=True)
class EntryPoint:
    """One of a project's PEP 621 entry points.

    ``kind`` is ``"cli"`` for ``[project.scripts]``, ``"gui"`` for
    ``[project.gui-scripts]``, and ``"other"`` for any
    ``[project.entry-points.<group>]``, whose group is kept in ``group``.
    """

    name: str
    reference: str
    kind: str
    group: str

    @property
    def label(self) -> str:
        """How the list describes the kind: Console, GUI, or the group's name."""
        return {"cli": "Console", "gui": "GUI"}.get(self.kind, self.group)


def project_entry_points(project_meta: Mapping[str, Any]) -> list[EntryPoint]:
    """Every entry point a ``[project]`` table declares, sorted by name."""
    found: list[EntryPoint] = []
    tables: list[tuple[str, str, Any]] = [
        ("cli", "console_scripts", project_meta.get("scripts", {})),
        ("gui", "gui_scripts", project_meta.get("gui-scripts", {})),
    ]
    other = project_meta.get("entry-points", {})
    if isinstance(other, Mapping):
        tables += [("other", group, table) for group, table in other.items()]
    for kind, group, table in tables:
        if not isinstance(table, Mapping):
            continue
        for name, reference in table.items():
            if isinstance(reference, str):
                found.append(EntryPoint(str(name), reference, kind, str(group)))
    return sorted(found, key=lambda e: (e.name.casefold(), e.name, e.group))


def scan_project(item: Path) -> dict[str, Any]:
    """Describe a project folder from its ``pyproject.toml``.

    ``[tool.stub_launcher] entry_point`` names the file to run. Without it,
    the project's PEP 621 entry points decide: one is run when the project is
    tapped, and several make the project a ``"package"`` that opens like a
    folder, listing them. A project with neither runs ``main.py``.
    """
    with open(item / "pyproject.toml", "rb") as f:
        toml_data = tomllib.load(f)

    # Read standard PEP 621 table
    project_meta = toml_data.get("project", {})
    name = project_meta.get("name", item.name)
    desc = project_meta.get("description", "Project directory module.")

    # Read tool overrides
    tool_meta = toml_data.get("tool", {}).get("stub_launcher", {})
    icon_relative = tool_meta.get("icon")

    row: dict[str, Any] = {
        "title": tool_meta.get("display_name", name),
        "subtitle": desc,
        "icon_path": item / icon_relative if icon_relative else None,
        # Target launch file path relative to its home folder
        "entry_point": item / tool_meta.get("entry_point", "main.py"),
        "folder_root": item / tool_meta.get("import_path", "src"),
        # PEP 621 dependencies list (default to empty list if missing)
        "dependencies": project_meta.get("dependencies", []),
        "aliases": parse_aliases(tool_meta.get("aliases", {})),
        "project_dir": item,
        "kind": "project",
    }
    if "entry_point" in tool_meta:
        return row
    entries = project_entry_points(project_meta)
    if len(entries) == 1:
        row["entry"] = entries[0]  # the project's implied entry point
    elif entries:
        del row["entry_point"]
        row["kind"] = "package"
        row["entries"] = entries
    return row


def entry_rows(package: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The rows listed inside a package with several entry points."""
    shared = ("folder_root", "project_dir", "dependencies", "aliases")
    return [
        {
            "title": entry.name,
            "subtitle": f"{entry.label} · {entry.reference}",
            "icon_path": None,
            "entry": entry,
            "package_title": package["title"],
            "kind": "entry",
            **{key: package[key] for key in shared},
        }
        for entry in package["entries"]
    ]


def folder_summary(folder: Path) -> str:
    """Summarise what the list would show inside `folder`, without parsing files.

    For example "2 subfolders, 1 package, 3 scripts, 1 other file", or
    "Empty folder". Hidden entries, caches and launcher files are not counted.
    This lists one directory per folder row, so it is cheap but not free.
    """
    counts = {"subfolder": 0, "package": 0, "script": 0, "other file": 0}
    try:
        children = list(folder.iterdir())
    except OSError:
        return "Folder"
    for child in children:
        if child.name.startswith("."):
            continue
        if child.is_dir():
            if (child / "pyproject.toml").exists():
                counts["package"] += 1
            elif child.name not in SKIPPED_FOLDERS:
                counts["subfolder"] += 1
        elif child.suffix == ".py":
            if child.name not in RESERVED_SCRIPTS:
                counts["script"] += 1
        else:
            counts["other file"] += 1
    parts = [f"{n} {kind}{'' if n == 1 else 's'}" for kind, n in counts.items() if n]
    return ", ".join(parts) if parts else "Empty folder"


def scan_folder(item: Path) -> dict[str, Any]:
    """Describe a plain folder that the launcher can navigate into."""
    return {
        "title": item.name,
        "subtitle": folder_summary(item),
        "icon_path": None,
        "folder": item,
        "dependencies": [],
        "kind": "folder",
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


def get_bundled_inventory(exclude: Path | None = None) -> dict[str, str]:
    """Return packages importable from ``sys.path``, excluding ``exclude``.

    The launcher prepends the user site-packages to ``sys.path`` after the first
    run, so exclude it here: those packages are user installs, not bundled ones.
    """
    excluded = exclude.resolve() if exclude else None
    paths = [
        p for p in sys.path if excluded is None or Path(p or ".").resolve() != excluded
    ]
    packages: dict[str, str] = {}
    for dist in importlib.metadata.distributions(path=paths):
        packages.setdefault(canonicalize_name(dist.metadata["Name"]), dist.version)
    return packages


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
