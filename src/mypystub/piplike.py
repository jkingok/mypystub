import asyncio
import hashlib
import importlib
import importlib.metadata
import logging
import shutil
import sys
import tempfile
import zipfile
from collections import deque
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anyio
import httpx2
import resolvelib
from installer import install
from installer.destinations import SchemeDictionaryDestination
from installer.sources import WheelFile
from packaging.requirements import Requirement
from packaging.tags import Tag, sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version
from unearth import PackageFinder, TargetPython
from unearth.link import Link

from . import direct_refs, git_hosts, git_updates, purity, source_build, source_installs
from .direct_refs import unsupported_message
from .maintenance import MaintenanceError
from .package_aliases import ALIASES, Alias, parse_aliases  # noqa: F401

log = logging.getLogger(__name__)


class DependencyError(Exception):
    """Raised when dependency resolution, downloading, or unpacking fails."""


@dataclass(frozen=True)
class Candidate:
    name: str
    version: Version
    link: Link | None = None
    is_system: bool = False
    # Already unpacked into the target site-packages by an earlier run
    is_installed: bool = False
    # A wheel the requirement itself pointed at (`foo @ https://...whl`, #171)
    is_direct: bool = False
    # Use frozenset for immutability so dataclass remains hashable
    requested_extras: frozenset[str] = frozenset()
    # The requirement name this candidate satisfies; differs from `name` when an
    # alias substitutes another distribution (pyyaml satisfied by pyyaml-pure)
    identifier: str = ""
    # The direct_url.json (PEP 610) to record when it's installed: where a
    # package from git came from, and the commit (#328). Not part of equality
    direct_url: str = field(default="", compare=False)

    def __post_init__(self):
        object.__setattr__(self, "name", canonicalize_name(self.name))
        object.__setattr__(
            self, "identifier", canonicalize_name(self.identifier or self.name)
        )

    def __str__(self) -> str:
        source = (
            "system"
            if self.is_system
            else "installed"
            if self.is_installed
            else "url"
            if self.is_direct
            else "pypi"
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
        supported_tags: Iterable[Tag] | None = None,
        backend_installer: source_build.BackendInstaller | None = None,
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
        # What this platform can run, for wheels the requirement names by URL
        self.supported_tags: frozenset[Tag] = frozenset(
            supported_tags if supported_tags is not None else sys_tags()
        )
        self._warned: set[str] = set()
        # Source URLs already built, and the URL each built wheel is cached under
        self._sources: dict[str, str] = {}
        # Installs a build backend's requirements into a folder (#257); tests
        # replace it, the app resolves them from PyPI like any requirement
        self.backend_installer = backend_installer or self.install_backend
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
        # A URL must never be quietly turned into the same name from PyPI
        for req in req_specs:
            if problem := unsupported_message(req):
                raise DependencyError(problem)

        # resolvelib maps identifier -> candidates already ruled out (backtracking)
        excluded: set[Candidate] = set(incompatibilities.get(identifier, ()))

        # Collect explicitly requested extras as a frozenset
        active_extras: frozenset[str] = frozenset(
            extra for req in req_specs if req.extras for extra in req.extras
        )

        # 0. A requirement that names a wheel by URL (#171) is that wheel, only
        if direct := [r for r in req_specs if r.url]:
            return self._direct_candidates(
                canon_id, direct, req_specs, excluded, active_extras
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
                # A package with a substitute isn't built from source: the
                # substitute is the answer for a platform with no wheel for it
                found = self._pypi_candidates(
                    canon_id,
                    canon_id,
                    req_specs,
                    excluded,
                    active_extras,
                    skip,
                    allow_source=substitute is None,
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
            log.info(message)

    def _pypi_candidates(
        self,
        canon_id: str,
        identifier: str,
        req_specs: list[Requirement],
        excluded: set[Candidate],
        active_extras: frozenset[str],
        skip: set[tuple[str, Version]],
        allow_source: bool = True,
    ) -> list[Candidate]:
        """Index candidates for `canon_id`, satisfying `identifier`, newest first.

        With no usable wheel, a source distribution is built unless
        `allow_source` is False.
        """
        try:
            matches = self.finder.find_matches(canon_id)
        except Exception as exc:
            # Offline, DNS failure, index error: name the package that needed it
            raise DependencyError(
                f"{canon_id} is not installed and the package index could not be "
                f"reached: {exc}"
            ) from exc

        candidates: list[Candidate] = []
        sources: list[Any] = []  # source distributions, for when no wheel will do
        for match in matches:
            if not match.version:
                continue
            if (canonicalize_name(match.name), Version(match.version)) in skip:
                continue

            filename = match.link.filename.lower()
            if filename.endswith(source_installs.ARCHIVE_SUFFIXES):
                sources.append(match)
                continue

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
        if not candidates and sources and allow_source:
            candidates = self._built_candidates(
                canon_id, identifier, req_specs, excluded, active_extras, sources
            )
        return candidates[: self.max_candidates]

    def _built_candidates(
        self,
        canon_id: str,
        identifier: str,
        req_specs: list[Requirement],
        excluded: set[Candidate],
        active_extras: frozenset[str],
        sources: list[Any],
    ) -> list[Candidate]:
        """A wheel built from the newest source distribution that fits (#257).

        Only when the index has no usable wheel of the package, as building
        takes longer than downloading. Built in-process with the project's own
        build backend, like a source archive a requirement names; a pure
        Python result installs, anything else is refused as it would be if it
        had been a wheel.
        """
        for match in sorted(sources, key=lambda m: Version(m.version), reverse=True):
            probe = Candidate(
                name=canonicalize_name(match.name),
                version=Version(match.version),
                requested_extras=active_extras,
                identifier=identifier,
            )
            if probe in excluded or not all(
                self.is_satisfied_by(req, probe) for req in req_specs
            ):
                continue
            url = match.link.url
            wheel_url = self._prepare_source(url, Requirement(canon_id))
            wheel = direct_refs.cache_path(self.cache_dir, wheel_url)
            name, version, _, _ = parse_wheel_filename(wheel.name)
            return [
                Candidate(
                    name=name,
                    version=version,
                    link=Link(wheel_url),
                    is_direct=True,
                    requested_extras=active_extras,
                    identifier=identifier,
                )
            ]
        return []

    def _direct_candidates(
        self,
        canon_id: str,
        direct: list[Requirement],
        req_specs: list[Requirement],
        excluded: set[Candidate],
        active_extras: frozenset[str],
    ) -> list[Candidate]:
        """The one wheel a requirement points at, after checking it fits (#171)."""
        urls = {direct_refs.urldefrag(r.url or "").url for r in direct}
        if len(urls) > 1:
            raise DependencyError(
                f"{canon_id} is pointed at more than one URL: "
                + ", ".join(sorted(urls))
            )
        if self.use_system and canon_id in self.system_packages:
            # As with a version: a second copy would shadow the app's own,
            # which is already imported. So a prototype that names the
            # bundled package by URL (to run standalone) uses the bundled one.
            log.info(
                f"{canon_id} is bundled with the app ("
                f"{self.system_packages[canon_id]}); using it instead of "
                + ", ".join(sorted(urls))
            )
            sys_cand = Candidate(
                name=canon_id,
                version=self.system_packages[canon_id],
                is_system=True,
                requested_extras=active_extras,
            )
            return [] if sys_cand in excluded else [sys_cand]
        requirement = direct[0]
        if direct_refs.kind_of(requirement.url or "") in ("archive", "git-host"):
            return self._source_candidates(
                canon_id, requirement, req_specs, excluded, active_extras
            )
        try:
            name, version = direct_refs.wheel_identity(requirement, self.supported_tags)
        except direct_refs.WheelProblem as problem:
            raise DependencyError(str(problem)) from None
        candidate = Candidate(
            name=name,
            version=version,
            link=Link(requirement.url or ""),  # keeps any #sha256= to check
            is_direct=True,
            requested_extras=active_extras,
            identifier=canon_id,
        )
        plain = [r for r in req_specs if not r.url]
        if candidate in excluded or not all(
            self.is_satisfied_by(r, candidate) for r in plain
        ):
            return []
        return [candidate]

    def _source_candidates(
        self,
        canon_id: str,
        requirement: Requirement,
        req_specs: list[Requirement],
        excluded: set[Candidate],
        active_extras: frozenset[str],
    ) -> list[Candidate]:
        """The wheel built from a source archive the requirement names (#257).

        Once built, it is a wheel at a URL like any other (#171): its metadata,
        purity check and install all take that path.
        """
        given = requirement.url or ""
        git = git_updates.requested(canon_id, given)
        commit = self._branch_commit(git) if git is not None else ""
        # The archive of the exact commit, so what's recorded is what's built
        pinned = git_updates.at_commit(given, commit) if commit else given
        url = git_hosts.archive_url(pinned) or given
        hint = git_hosts.archive_url(given) or given  # the ref names the version
        wheel_url = self._prepare_source(url, requirement, hint, commit)
        if git is not None and not commit:
            # The host couldn't say; a GitHub zip keeps its commit itself
            archive = direct_refs.cache_path(self.cache_dir, url)
            commit = source_installs.commit_of(archive)
        wheel = direct_refs.cache_path(self.cache_dir, wheel_url)
        name, version, _, _ = parse_wheel_filename(wheel.name)
        candidate = Candidate(
            name=name,
            version=version,
            link=Link(wheel_url),
            is_direct=True,
            requested_extras=active_extras,
            identifier=canon_id,
            direct_url=git_updates.direct_url_json(git, commit)
            if git is not None and commit
            else "",
        )
        plain = [r for r in req_specs if not r.url]
        if candidate in excluded or not all(
            self.is_satisfied_by(r, candidate) for r in plain
        ):
            return []
        return [candidate]

    def _branch_commit(self, source: git_updates.GitSource) -> str:
        """The commit `source`'s ref names now, or "" if the host can't say.

        A commit given in the requirement is used as it is.
        """
        if source.ref and git_updates.FULL_SHA.fullmatch(source.ref):
            return source.ref.lower()
        try:
            return git_updates.latest_commit(self.http_client, source) or ""
        except MaintenanceError as error:
            log.warning(f"Couldn't find {source.url}'s commit: {error}")
            return ""

    def _prepare_source(
        self,
        url: str,
        requirement: Requirement,
        hint_url: str | None = None,
        commit: str = "",
    ) -> str:
        """Download, unpack and build a source archive (cached); the wheel's URL.

        The wheel is kept where a wheel at its URL would be (``cache_path``),
        under a URL made from the source's, so nothing downloads it again.
        """
        if url in self._sources:
            return self._sources[url]
        archive = direct_refs.cache_path(self.cache_dir, url)
        if not archive.exists():
            try:
                response = self.http_client.get(
                    direct_refs.urldefrag(url).url, follow_redirects=True
                )
                response.raise_for_status()
            except httpx2.HTTPError as exc:
                raise DependencyError(f"Couldn't download {url}: {exc}") from exc
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_bytes(response.content)
        try:
            direct_refs.check_sha256(archive, url)
            root = source_installs.open_source(archive, url)
            system = source_build.build_system(root)
            site = self.backend_site(system.requires)
            built = source_build.build_wheel(
                root,
                site,
                archive.parent / "built",
                source_installs.version_hint(
                    root,
                    hint_url or url,
                    commit or source_installs.commit_of(archive),
                ),
                system,
            )
        except (
            direct_refs.WheelProblem,
            source_installs.SourceProblem,
            source_build.BuildProblem,
        ) as problem:
            if isinstance(problem, direct_refs.WheelProblem):
                archive.unlink(missing_ok=True)  # a wrong hash: don't keep the file
            raise DependencyError(
                f"Can't install “{requirement}”: {problem}."
            ) from None
        name, _, _, _ = parse_wheel_filename(built.name)
        if requirement.name and canonicalize_name(requirement.name) != name:
            raise DependencyError(
                f"Can't install “{requirement}”: the source is {name}, "
                f"not {requirement.name}."
            )
        wheel_url = f"{direct_refs.urldefrag(url).url}/{built.name}"
        target = direct_refs.cache_path(self.cache_dir, wheel_url)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(built, target)
        self._sources[url] = wheel_url
        return wheel_url

    def backend_site(self, requires: tuple[str, ...]) -> Path:
        """A folder with a build backend's requirements installed, made once.

        Kept beside the user's packages, by requirements, so the next build
        with the same backend needs no network. Only fetched when a source
        needs it (backends aren't bundled with the app, so they can update).
        """
        key = hashlib.sha256("\n".join(sorted(requires)).encode()).hexdigest()[:16]
        base = self.target_dir.parent if self.target_dir else self.cache_dir
        site = base / "build_backends" / key
        if (site / ".complete").exists():
            return site
        shutil.rmtree(site, ignore_errors=True)
        site.mkdir(parents=True)
        try:
            self.backend_installer(requires, site)
        except DependencyError as error:
            shutil.rmtree(site, ignore_errors=True)
            raise source_build.BuildProblem(
                f"its build backend can't be installed: {error}"
            ) from None
        (site / ".complete").write_text("\n".join(requires) + "\n", encoding="utf-8")
        return site

    def install_backend(self, requires: tuple[str, ...], site: Path) -> None:
        """Resolve a backend's requirements from PyPI and unpack them into `site`.

        Pure wheels only, nothing bundled taken for them (the backend gets its
        own copies), and no source builds: a backend has to come as wheels.
        """
        provider = PyPIWheelProvider(
            finder=self.finder,
            cache_dir=self.cache_dir,
            system_packages={},
            http_client=self.http_client,
            use_system=False,
            max_candidates=self.max_candidates,
            target_dir=site,
            supported_tags=self.supported_tags,
        )
        try:
            result = resolvelib.Resolver(provider, resolvelib.BaseReporter()).resolve(
                [Requirement(r) for r in requires]
            )
        except resolvelib.ResolutionError as error:
            raise DependencyError(str(error)) from error
        for candidate in result.mapping.values():
            if candidate.link is None:
                continue
            wheel = (
                direct_refs.cache_path(self.cache_dir, candidate.link.url)
                if candidate.is_direct
                else self.cache_dir / candidate.link.filename
            )
            if not wheel.exists():
                try:
                    response = self.http_client.get(
                        direct_refs.urldefrag(candidate.link.url).url,
                        follow_redirects=True,
                    )
                    response.raise_for_status()
                except httpx2.HTTPError as exc:
                    raise DependencyError(f"Couldn't download {candidate}: {exc}")
                wheel.parent.mkdir(parents=True, exist_ok=True)
                wheel.write_bytes(response.content)
            if reason := purity.wheel_impurity(wheel):
                raise DependencyError(f"{candidate.name} isn't pure Python ({reason})")
            unpack_wheel(wheel, site)

    def _direct_wheel_metadata(self, candidate: Candidate) -> str:
        """The METADATA of a wheel at a URL: downloaded once, then read from disk."""
        assert candidate.link is not None
        url = candidate.link.url
        path = direct_refs.cache_path(self.cache_dir, url)
        if not path.exists():
            try:
                response = self.http_client.get(
                    direct_refs.urldefrag(url).url, follow_redirects=True
                )
                response.raise_for_status()
            except httpx2.HTTPError as exc:
                raise DependencyError(f"Couldn't download {url}: {exc}") from exc
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(response.content)
        try:
            direct_refs.check_sha256(path, url)
        except direct_refs.WheelProblem as problem:
            path.unlink(missing_ok=True)
            raise DependencyError(str(problem)) from None
        try:
            with zipfile.ZipFile(path) as wheel:
                for member in wheel.namelist():
                    if member.endswith(".dist-info/METADATA"):
                        return wheel.read(member).decode("utf-8", "replace")
        except zipfile.BadZipFile as exc:
            path.unlink(missing_ok=True)
            raise DependencyError(f"{path.name} isn't a valid wheel: {exc}") from exc
        return ""

    def _warn_if_bundled_mismatch(self, req: Requirement, cand: Candidate) -> None:
        """Log once when a bundled package doesn't meet a script's specifier."""
        if (
            req.specifier
            and not req.specifier.contains(cand.version, prereleases=True)
            and cand.name not in self._warned
        ):
            self._warned.add(cand.name)
            log.warning(
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
        if (
            candidate.is_direct
            and candidate.version.public == "0"
            and candidate.version.local is not None
        ):
            return True  # built from source that doesn't say, asked for by URL
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
        if candidate.is_direct:
            return self._direct_wheel_metadata(candidate)
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
        log.info("[Resolver] Starting dependency graph resolution...")

    def starting_round(self, index: int) -> None:
        log.info(f"[Resolver] Round {index}...")

    def pinning(self, candidate) -> None:
        log.info(f"[Resolver] -> Pinned candidate: {candidate}")
        if self.on_progress:
            self.on_progress(f"Resolved {candidate.name} {candidate.version}")

    def rejecting_candidate(self, criterion, candidate) -> None:
        log.info(f"[Resolver] -> Backtracking: Rejected {candidate}")


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


def moved_on(installed: importlib.metadata.Distribution, candidate: Candidate) -> bool:
    """Whether a package from git is installed at another commit than `candidate`.

    Its version can stay the same from commit to commit, so the commit
    recorded in ``direct_url.json`` decides (#328).
    """
    if not candidate.direct_url:
        return False
    now = git_updates.source_from(candidate.name, candidate.direct_url)
    was = git_updates.source_from(
        candidate.name, installed.read_text("direct_url.json")
    )
    return now is not None and (was is None or was.commit != now.commit)


def unpack_wheel(
    wheel_path: Path, target_site_packages: Path, direct_url: str = ""
) -> None:
    """Install a wheel into `target_site_packages`.

    `direct_url`, if given, is written into its dist-info as
    ``direct_url.json`` (PEP 610), as pip does for an install from git.
    """
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
        extra = {"direct_url.json": direct_url.encode()} if direct_url else {}
        install(source=source, destination=destination, additional_metadata=extra)


# Main Async Entry Point


async def install_resolved(
    mapping: Mapping[str, Candidate],
    target_dir: Path,
    cache_dir: Path,
    require_pure: bool,
    force_reinstall: bool = False,
    progress: Callable[[str], None] = lambda message: None,
    on_count: Callable[[int, int], None] | None = None,
) -> int:
    """Install what was resolved, returning how many: all of it, or nothing.

    Every wheel is fetched and checked first, so a refused one can't leave the
    packages that depend on it installed without it. `on_count` gets each step
    done of the total: first through the packages to fetch and check, then,
    starting again, through those to install.
    """
    count = on_count or (lambda done, total: None)
    pending: list[tuple[Candidate, Path, Any]] = []
    wanted = [c for c in mapping.values() if not (c.is_system or c.is_installed)]
    async with httpx2.AsyncClient(timeout=30.0) as async_http:
        for done, candidate in enumerate(wanted):
            count(done, len(wanted))
            installed = await asyncio.to_thread(
                get_installed_distribution, target_dir, candidate.name
            )
            if (
                installed
                and Version(installed.version) == candidate.version
                and not force_reinstall
                and not moved_on(installed, candidate)
            ):
                continue
            link = candidate.link
            assert link is not None  # only system packages have none
            wheel_path = (
                direct_refs.cache_path(cache_dir, link.url)
                if candidate.is_direct
                else cache_dir / link.filename
            )
            # A wheel built from source is already here (#257)
            if not wheel_path.exists():
                wheel_path.parent.mkdir(parents=True, exist_ok=True)
                log.info(f"downloading {link}")
                progress(f"Downloading {candidate.name} {candidate.version}")
                await download_wheel_async(
                    async_http, direct_refs.urldefrag(link.url).url, wheel_path
                )
            # Only pure Python is installed at run time (#172)
            if require_pure and (reason := purity.wheel_impurity(wheel_path)):
                raise DependencyError(
                    f"{candidate.name} {candidate.version} can't be installed: "
                    f"{reason}. Only pure Python is installed at run time; "
                    "compiled packages have to be bundled with the app."
                )
            pending.append((candidate, wheel_path, installed))

    for done, (candidate, wheel_path, installed) in enumerate(pending):
        count(done, len(pending))
        if installed:
            log.info(
                f"upgrading {candidate.name} from {installed.version} "
                f"to {candidate.version}"
            )
            progress(f"Removing {candidate.name} {installed.version}")
            await asyncio.to_thread(
                remove_installed_package, target_dir, candidate.name
            )
        progress(f"Installing {candidate.name} {candidate.version}")
        try:
            await asyncio.to_thread(
                unpack_wheel, wheel_path, target_dir, candidate.direct_url
            )
        except (zipfile.BadZipFile, OSError) as exc:
            raise DependencyError(f"Failed to unpack {wheel_path.name}: {exc}") from exc
    if pending:
        count(len(pending), len(pending))
    return len(pending)


def pure_only_by_default(platform_name: str) -> bool:
    """Whether only pure-Python wheels install when the caller doesn't say.

    Phones and tablets run compiled code only from wheels built into the app,
    so iOS and Android refuse anything else. On desktop the rule is opt-in.
    """
    return platform_name in ("ios", "android")


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
    pure_only: bool | None = None,
    on_count: Callable[[int, int], None] | None = None,
) -> None:
    """
    Async dependency resolver and installer compatible with Toga / asyncio event loops.

    Blocking work (resolution, metadata scans, unpacking) runs in worker threads.
    `on_progress` receives short status messages, always on the event loop thread,
    so it may update widgets directly, as does `on_count` (steps done of the
    total, while fetching and then installing; see install_resolved), which
    ends with ``(0, 0)``: nothing left to count. `aliases` (from launcher.toml or the
    script) are merged over the built-in ALIASES.
    """
    loop = asyncio.get_running_loop()

    def progress(message: str) -> None:
        log.info(f"[Progress] {message}")
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
            log.info(f"Temporary wheel cache is {cache_dir}")
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
            log.info(f"will clean {target_dir}")
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
                # Wheels first; a package with none is built from its source
                # distribution (_built_candidates)
                prefer_binary={":all:"},
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

        changed = await install_resolved(
            resolution.mapping,
            target_dir,
            cache_dir,
            pure_only_by_default(sys.platform) if pure_only is None else pure_only,
            force_reinstall,
            progress,
            on_count,
        )
        if changed:
            # Python may have cached "nothing here" for target_dir while it was
            # missing or empty; forget that so the new packages can be imported
            importlib.invalidate_caches()
        log.info("successfully met all requirements")
        progress("Dependencies ready" if changed else "Dependencies already satisfied")
    finally:
        if on_count:
            on_count(0, 0)  # finished, or failed: nothing left to count
        if is_temp_cache and cache_dir.exists():
            log.info("removing temporary wheel cache")
            await asyncio.to_thread(shutil.rmtree, cache_dir, True)


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

    A run puts the user site-packages on ``sys.path``, so exclude it here:
    those packages are user installs, not bundled ones.
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
