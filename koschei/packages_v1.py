"""Koschei Packages v1, phase 1: pinned package sources without a registry.

See ``docs/PACKAGES_V1.md``. A project lists its dependencies in
``koschei.toml``; ``ks pkg sync`` copies each package's ``.ks`` sources and
manifest into ``.koschei/packages/``, computes its capability surface with the
compiler's capability analysis, and records digest and surface in
``koschei.packages.lock.json``. A later sync that would widen a package's
surface is refused unless the author passes ``--allow <capability>``.

Every module graph load inside such a project verifies the lock and the
vendored bytes first, so a package that changes on disk after sync fails
closed instead of being compiled.

Nothing in a package runs while it is fetched, inspected or compiled: the
only programs started here are ``git`` (with hooks and submodules disabled)
for git sources.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .ast_nodes import SourceLocation

LOCK_NAME = "koschei.packages.lock.json"
LOCK_SCHEMA = "koschei.packages-lock/v1"
VENDOR_PARTS = (".koschei", "packages")
MANIFEST_NAME = "koschei.toml"
CODE = "KS1606"
PACKAGE_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
DEFAULT_REGISTRY = "https://koschei.dev/registry"
TREE_CONTEXT = b"koschei.package-tree/v1\x00"
SURFACE_ORDER = (
    "disk", "net", "env", "process", "serve", "persist", "input", "clock", "random", "db",
)
_ORIGIN = SourceLocation(1, 1)


class PackageError(ValueError):
    """A dependency, the package lock or a vendored package is not acceptable."""


# --- manifest -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DependencySpec:
    name: str
    path: str | None = None
    git: str | None = None
    rev: str | None = None
    version: str | None = None
    registry: str | None = None

    def source(self) -> dict[str, str]:
        if self.path is not None:
            return {"path": self.path}
        if self.version is not None:
            return {"registry": str(self.registry), "version": self.version}
        return {"git": str(self.git), "rev": str(self.rev)}


@dataclass(frozen=True, slots=True)
class ProjectPackages:
    root: Path
    dependencies: dict[str, DependencySpec]
    deny: frozenset[str]
    registry: str = DEFAULT_REGISTRY


def _read_toml(manifest: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise PackageError(f"cannot read {manifest}: {error}") from error


def parse_dependencies(data: dict[str, Any], where: str) -> dict[str, DependencySpec]:
    table = data.get("dependencies", {})
    if not isinstance(table, dict):
        raise PackageError(f"{where}: [dependencies] must be a table")
    result: dict[str, DependencySpec] = {}
    for name, value in table.items():
        if not PACKAGE_NAME.fullmatch(name):
            raise PackageError(f"{where}: invalid dependency name {name!r}")
        if not isinstance(value, dict):
            raise PackageError(
                f"{where}: dependency {name!r} must be a table such as "
                '{ version = "1.2.0" }, { path = "..." } or '
                '{ git = "https://...", rev = "<40-hex commit>" }'
            )
        keys = set(value)
        if keys == {"version"}:
            if not isinstance(value["version"], str) or not VERSION.fullmatch(value["version"]):
                raise PackageError(
                    f"{where}: dependency {name!r}: version must be an exact MAJOR.MINOR.PATCH"
                )
            result[name] = DependencySpec(name, version=value["version"])
        elif keys == {"path"} and isinstance(value["path"], str) and value["path"]:
            result[name] = DependencySpec(name, path=value["path"])
        elif keys == {"git", "rev"}:
            git, rev = value["git"], value["rev"]
            if not isinstance(git, str) or not git.startswith("https://"):
                raise PackageError(f"{where}: dependency {name!r}: git must be an https:// URL")
            if not isinstance(rev, str) or not COMMIT.fullmatch(rev):
                raise PackageError(
                    f"{where}: dependency {name!r}: rev must be a full 40-character "
                    "commit hash; branches and tags can move"
                )
            result[name] = DependencySpec(name, git=git, rev=rev)
        else:
            raise PackageError(
                f"{where}: dependency {name!r} needs exactly 'version', exactly 'path', "
                "or exactly 'git' and 'rev'"
            )
    return result


def load_project_packages(root: Path) -> ProjectPackages:
    root = root.resolve()
    data = _read_toml(root / MANIFEST_NAME)
    policy = data.get("policy", {})
    if not isinstance(policy, dict):
        raise PackageError("[policy] must be a table")
    deny = policy.get("deny", [])
    if not isinstance(deny, list) or any(item not in SURFACE_ORDER for item in deny):
        raise PackageError(f"policy.deny must list capabilities from: {', '.join(SURFACE_ORDER)}")
    registry_table = data.get("registry", {})
    if not isinstance(registry_table, dict) or set(registry_table) - {"url"}:
        raise PackageError("[registry] may only set url")
    registry = registry_table.get("url") or os.environ.get("KOSCHEI_REGISTRY") or DEFAULT_REGISTRY
    if not isinstance(registry, str) or not registry.startswith(("https://", "file://")):
        raise PackageError("registry url must start with https:// or file://")
    registry = registry.rstrip("/")
    dependencies = {
        name: _with_registry(spec, registry)
        for name, spec in parse_dependencies(data, MANIFEST_NAME).items()
    }
    return ProjectPackages(root, dependencies, frozenset(deny), registry)


def _with_registry(spec: DependencySpec, registry: str) -> DependencySpec:
    if spec.version is None:
        return spec
    return DependencySpec(spec.name, version=spec.version, registry=registry)


# --- package trees ----------------------------------------------------------


def _is_package_file(relative: Path) -> bool:
    return relative.suffix == ".ks" or relative.as_posix() == MANIFEST_NAME


def package_files(root: Path) -> list[str]:
    """Return the package's source files: every ``.ks`` file and ``koschei.toml``.

    Symlinks are refused rather than followed; ``.git`` and ``.koschei`` are
    skipped; every other file (scripts, binaries, documents) is ignored and never
    copied into a project.
    """

    files: list[str] = []
    for directory, subdirectories, names in os.walk(root):
        here = Path(directory)
        kept = []
        for sub in sorted(subdirectories):
            if (here / sub).is_symlink():
                raise PackageError(f"package contains a symlinked directory: {(here / sub).relative_to(root)}")
            if sub not in {".git", ".koschei"}:
                kept.append(sub)
        subdirectories[:] = kept
        for name in names:
            path = here / name
            relative = path.relative_to(root)
            if not _is_package_file(relative):
                continue
            if path.is_symlink() or not path.is_file():
                raise PackageError(f"package file is not a regular file: {relative.as_posix()}")
            files.append(relative.as_posix())
    if MANIFEST_NAME not in files:
        raise PackageError(f"package has no {MANIFEST_NAME}")
    return sorted(files)


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256(TREE_CONTEXT)
    for relative in package_files(root):
        content = (root / relative).read_bytes()
        digest.update(relative.encode("utf-8") + b"\x00")
        digest.update(hashlib.sha256(content).digest())
    return digest.hexdigest()


def _copy_package(source: Path, destination: Path) -> None:
    for relative in package_files(source):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)


def _git_fetch(spec: DependencySpec, destination: Path) -> None:
    git = shutil.which("git")
    if git is None:
        raise PackageError(f"dependency {spec.name!r} uses git, but git is not installed")
    environment = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1")
    base = [
        git,
        "-c", "core.hooksPath=/dev/null",
        "-c", "core.symlinks=false",
        "-c", "submodule.recurse=false",
        "-c", "protocol.file.allow=never",
        "-c", "advice.detachedHead=false",
    ]
    steps = (
        ["init", "--quiet", str(destination)],
        ["-C", str(destination), "fetch", "--quiet", "--depth", "1", str(spec.git), str(spec.rev)],
        ["-C", str(destination), "checkout", "--quiet", "FETCH_HEAD"],
    )
    for step in steps:
        completed = subprocess.run(
            [*base, *step], capture_output=True, text=True, env=environment, timeout=300
        )
        if completed.returncode != 0:
            raise PackageError(
                f"dependency {spec.name!r}: git {step[2] if step[0] == '-C' else step[0]} failed: "
                f"{completed.stderr.strip()[:400]}"
            )
    head = subprocess.run(
        [*base, "-C", str(destination), "rev-parse", "HEAD"],
        capture_output=True, text=True, env=environment, timeout=60,
    ).stdout.strip()
    if head != spec.rev:
        raise PackageError(f"dependency {spec.name!r}: fetched commit {head} is not {spec.rev}")


# --- inspection -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InspectedPackage:
    name: str
    version: str
    entry: str
    digest: str
    surface: tuple[str, ...]
    dependencies: dict[str, DependencySpec]
    source: dict[str, str]


def _package_manifest(root: Path, expected: str) -> tuple[str, str, str, dict[str, DependencySpec], list | None]:
    data = _read_toml(root / MANIFEST_NAME)
    package = data.get("package")
    if not isinstance(package, dict):
        raise PackageError(f"package {expected!r}: {MANIFEST_NAME} has no [package] table")
    name, version = package.get("name"), package.get("version")
    entry = package.get("entry", "src/main.ks")
    if name != expected:
        raise PackageError(f"dependency {expected!r} contains package {name!r}; the names must match")
    if not isinstance(version, str) or not version:
        raise PackageError(f"package {expected!r}: package.version is required")
    if not isinstance(entry, str) or not entry.endswith(".ks"):
        raise PackageError(f"package {expected!r}: package.entry must be a .ks path")
    entry_path = (root / entry).resolve()
    try:
        entry_path.relative_to(root.resolve())
    except ValueError as error:
        raise PackageError(f"package {expected!r}: package.entry escapes the package") from error
    declared = package.get("surface")
    if declared is not None and (
        not isinstance(declared, list) or any(item not in SURFACE_ORDER for item in declared)
    ):
        raise PackageError(f"package {expected!r}: package.surface must list capability names")
    return name, version, Path(entry).as_posix(), parse_dependencies(data, f"package {expected!r}"), declared


def compute_surface(graph) -> tuple[str, ...]:
    from .capabilities import analyze_graph

    manifest = analyze_graph(graph)
    if manifest.main_has_capabilities or manifest.grants:
        raise PackageError(
            "a package cannot receive SystemCaps or narrow root authority; "
            "it can only use capabilities its caller passes in"
        )
    return tuple(domain for domain in SURFACE_ORDER if domain in manifest.domains())


# --- lock -------------------------------------------------------------------


@dataclass(slots=True)
class PackageLock:
    packages: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_json(self) -> str:
        payload = {"schema": LOCK_SCHEMA, "packages": self.packages}
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _vendor_root(project_root: Path) -> Path:
    return project_root.joinpath(*VENDOR_PARTS)


def vendor_dir(project_root: Path, name: str, digest: str) -> Path:
    return _vendor_root(project_root) / f"{name}-{digest[:16]}"


def load_lock(project_root: Path) -> PackageLock | None:
    path = project_root / LOCK_NAME
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PackageError(f"{LOCK_NAME} is not valid JSON: {error}") from error
    if not isinstance(payload, dict) or set(payload) != {"schema", "packages"} or payload["schema"] != LOCK_SCHEMA:
        raise PackageError(f"{LOCK_NAME} has an unknown format")
    packages = payload["packages"]
    if not isinstance(packages, dict):
        raise PackageError(f"{LOCK_NAME}: packages must be an object")
    required = {"version", "entry", "source", "digest", "surface", "dependencies"}
    for name, entry in packages.items():
        if not PACKAGE_NAME.fullmatch(name) or not isinstance(entry, dict) or set(entry) != required:
            raise PackageError(f"{LOCK_NAME}: entry {name!r} is malformed")
        if not isinstance(entry["digest"], str) or not DIGEST.fullmatch(entry["digest"]):
            raise PackageError(f"{LOCK_NAME}: entry {name!r} has a malformed digest")
        if not isinstance(entry["surface"], list) or any(item not in SURFACE_ORDER for item in entry["surface"]):
            raise PackageError(f"{LOCK_NAME}: entry {name!r} has a malformed surface")
        if not isinstance(entry["dependencies"], list) or any(dep not in packages for dep in entry["dependencies"]):
            raise PackageError(f"{LOCK_NAME}: entry {name!r} names an unlocked dependency")
    return PackageLock(dict(packages))


# --- sync -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SyncChange:
    name: str
    kind: str  # added | updated | unchanged | removed
    version: str
    surface: tuple[str, ...]
    previous_surface: tuple[str, ...] = ()

    @property
    def added_capabilities(self) -> tuple[str, ...]:
        return tuple(item for item in self.surface if item not in self.previous_surface)


@dataclass(frozen=True, slots=True)
class SyncResult:
    changes: tuple[SyncChange, ...]
    lock: PackageLock


class SurfaceWidened(PackageError):
    def __init__(self, changes: list[SyncChange]) -> None:
        self.changes = changes
        lines = [
            f"{change.name} {change.version} adds: {', '.join(change.added_capabilities)}"
            for change in changes
        ]
        flags = sorted({cap for change in changes for cap in change.added_capabilities})
        super().__init__(
            "update refused, a package would gain capabilities:\n  "
            + "\n  ".join(lines)
            + "\nto accept, run again with "
            + " ".join(f"--allow {cap}" for cap in flags)
        )


class PolicyDenied(PackageError):
    pass


def sync(project_root: str | Path, *, allow: frozenset[str] = frozenset()) -> SyncResult:
    """Fetch, inspect and lock every dependency; refuse a widened surface.

    Nothing is written unless every package is accepted.
    """

    from .modules import ModuleError, check_graph, load_graph
    from .semantic import SemanticError

    project = load_project_packages(Path(project_root))
    root = project.root
    previous = load_lock(root) or PackageLock()
    staging = Path(tempfile.mkdtemp(prefix=".pkg-sync-", dir=root))
    try:
        fetched: dict[str, tuple[DependencySpec, Path]] = {}
        registry_entries: dict[str, dict[str, Any]] = {}
        pending = list(project.dependencies.values())
        while pending:
            spec = _with_registry(pending.pop(0), project.registry)
            if spec.name in fetched:
                if fetched[spec.name][0].source() != spec.source():
                    raise PackageError(
                        f"two packages require {spec.name!r} from different sources; v1 allows one"
                    )
                continue
            raw = staging / "raw" / spec.name
            if spec.version is not None:
                from .registry_v1 import fetch_package

                old = previous.packages.get(spec.name)
                locked = old["digest"] if old and old["source"] == spec.source() else None
                raw.mkdir(parents=True)
                registry_entries[spec.name] = fetch_package(
                    str(spec.registry), spec.name, spec.version, raw, locked_digest=locked
                )
                source_dir = raw
            elif spec.path is not None:
                source_dir = (root / spec.path).resolve()
                if not source_dir.is_dir():
                    raise PackageError(f"dependency {spec.name!r}: {spec.path} is not a directory")
                if _vendor_root(root) in (source_dir, *source_dir.parents):
                    raise PackageError(f"dependency {spec.name!r} cannot point into {'/'.join(VENDOR_PARTS)}")
            else:
                raw.parent.mkdir(parents=True, exist_ok=True)
                _git_fetch(spec, raw)
                source_dir = raw
            clean = staging / "clean" / spec.name
            _copy_package(source_dir, clean)
            fetched[spec.name] = (spec, clean)
            _, _, _, nested, _ = _package_manifest(clean, spec.name)
            if spec.version is not None and any(dep.version is None for dep in nested.values()):
                raise PackageError(
                    f"registry package {spec.name!r} has non-registry dependencies"
                )
            if spec.git is not None and any(dep.path is not None for dep in nested.values()):
                raise PackageError(
                    f"git package {spec.name!r} has path dependencies; a fetched package "
                    "can only depend on git sources"
                )
            if spec.path is not None:
                # A path dependency's own path dependencies are relative to it.
                nested = {
                    name: DependencySpec(name, path=os.path.relpath((source_dir / dep.path).resolve(), root))
                    if dep.path is not None else dep
                    for name, dep in nested.items()
                }
            pending.extend(nested.values())

        inspected: dict[str, InspectedPackage] = {}
        for name, (spec, clean) in fetched.items():
            _, version, entry, nested, _ = _package_manifest(clean, name)
            digest = tree_digest(clean)
            inspected[name] = InspectedPackage(name, version, entry, digest, (), nested, spec.source())

        staged_vendor = staging / "vendor"
        for name, package in inspected.items():
            shutil.copytree(fetched[name][1], staged_vendor / f"{name}-{package.digest[:16]}")

        lock = PackageLock({
            name: {
                "version": package.version,
                "entry": package.entry,
                "source": package.source,
                "digest": package.digest,
                "surface": [],
                "dependencies": sorted(package.dependencies),
            }
            for name, package in inspected.items()
        })

        # Surfaces need the import resolver over the staged vendor tree.
        resolver = PackageImportResolver(staged_vendor, lock, direct={}, project_root=None)
        for name, package in inspected.items():
            entry_path = staged_vendor / f"{name}-{package.digest[:16]}" / package.entry
            try:
                graph = load_graph(entry_path, import_resolver=resolver)
            except ModuleError as error:
                raise PackageError(f"package {name!r} does not load: {error}") from error
            try:
                check_graph(graph)
            except (ModuleError, SemanticError) as error:
                raise PackageError(f"package {name!r} does not check: {error}") from error
            surface = compute_surface(graph)
            _, _, _, _, declared = _package_manifest(fetched[name][1], name)
            if declared is not None and tuple(x for x in SURFACE_ORDER if x in declared) != surface:
                raise PackageError(
                    f"package {name!r} declares surface {declared} but the compiler computes "
                    f"{list(surface)}"
                )
            lock.packages[name]["surface"] = list(surface)
            listed = registry_entries.get(name)
            if listed is not None and tuple(listed["surface"]) != surface:
                raise PackageError(
                    f"registry lists {name} {package.version} with surface {listed['surface']}, "
                    f"but the compiler computes {list(surface)}; refusing it"
                )

        denied = [
            f"{name}: {', '.join(sorted(set(entry['surface']) & project.deny))}"
            for name, entry in sorted(lock.packages.items())
            if set(entry["surface"]) & project.deny
        ]
        if denied:
            raise PolicyDenied(
                "refused by [policy] deny in koschei.toml:\n  " + "\n  ".join(denied)
            )

        changes: list[SyncChange] = []
        widened: list[SyncChange] = []
        for name, entry in sorted(lock.packages.items()):
            surface = tuple(entry["surface"])
            old = previous.packages.get(name)
            if old is None:
                changes.append(SyncChange(name, "added", entry["version"], surface))
                continue
            kind = "unchanged" if old["digest"] == entry["digest"] else "updated"
            change = SyncChange(name, kind, entry["version"], surface, tuple(old["surface"]))
            changes.append(change)
            if set(change.added_capabilities) - allow:
                widened.append(change)
        for name, old in sorted(previous.packages.items()):
            if name not in lock.packages:
                changes.append(SyncChange(name, "removed", old["version"], (), tuple(old["surface"])))
        if widened:
            raise SurfaceWidened(widened)

        vendor = _vendor_root(root)
        vendor.mkdir(parents=True, exist_ok=True)
        wanted = {f"{name}-{entry['digest'][:16]}" for name, entry in lock.packages.items()}
        for item in staged_vendor.iterdir() if staged_vendor.exists() else ():
            target = vendor / item.name
            if target.exists():
                shutil.rmtree(target)
            item.rename(target)
        for existing in vendor.iterdir():
            if existing.name not in wanted:
                shutil.rmtree(existing)
        temporary_lock = root / (LOCK_NAME + ".tmp")
        temporary_lock.write_text(lock.to_json(), encoding="utf-8")
        temporary_lock.replace(root / LOCK_NAME)
        return SyncResult(tuple(changes), lock)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


# --- resolution ---------------------------------------------------------------


class PackageImportResolver:
    """Resolve ``import name`` to a declared, locked and verified package.

    An importer sees only its own direct dependencies: the project's
    ``[dependencies]``, or a package's own as recorded in the lock.
    """

    def __init__(
        self,
        vendor: Path,
        lock: PackageLock,
        *,
        direct: dict[str, DependencySpec],
        project_root: Path | None,
    ) -> None:
        self.vendor = vendor.resolve(strict=False)
        self.lock = lock
        self.direct = direct
        self.project_root = project_root.resolve() if project_root else None
        self.package_roots = {
            name: (self.vendor / f"{name}-{entry['digest'][:16]}")
            for name, entry in lock.packages.items()
        }

    def _owner(self, importer: Path) -> tuple[Path, set[str]]:
        resolved = importer.resolve(strict=False)
        for name, package_root in self.package_roots.items():
            if package_root in resolved.parents:
                return package_root, set(self.lock.packages[name]["dependencies"])
        if self.project_root is not None and self.project_root in resolved.parents:
            return self.project_root, set(self.direct)
        return resolved.parent, set()

    def entry_of(self, name: str) -> Path:
        return self.package_roots[name] / self.lock.packages[name]["entry"]

    def __call__(self, importer: Path, name: str, location: SourceLocation) -> Path:
        from .core_library_v1 import core_library_module
        from .modules import MODULE_SUFFIX, ModuleError, _resolve_sibling_import

        owner_root, visible = self._owner(importer)
        if name in visible:
            local = importer.parent / (name + MODULE_SUFFIX)
            if local.exists():
                raise ModuleError(
                    "KS1601",
                    f"Ambiguous import '{name}': both {local.name} and a dependency named "
                    f"'{name}' exist. Shadowing is refused; rename one.",
                    location,
                )
            if core_library_module(name) is not None:
                raise ModuleError(
                    "KS1601",
                    f"Ambiguous import '{name}': a dependency has the name of a Core "
                    "Library module. Shadowing is refused.",
                    location,
                )
            return self.entry_of(name)
        if name in self.package_roots and owner_root != self.package_roots[name]:
            raise ModuleError(
                CODE,
                f"Package '{name}' is not a direct dependency here; declare it in "
                f"[dependencies] of the importing project or package.",
                location,
            )
        resolved = _resolve_sibling_import(importer, name, location)
        if core_library_module(name) is None:
            try:
                resolved.resolve(strict=False).relative_to(owner_root)
            except ValueError:
                raise ModuleError("KS1601", f"Import '{name}' escapes its package", location)
        return resolved


def _find_project_root(start: Path) -> Path | None:
    for directory in (start, *start.parents):
        if (directory / MANIFEST_NAME).is_file():
            return directory
    return None


def verify_project(project_root: Path) -> PackageImportResolver:
    """Check the lock against koschei.toml and every vendored byte."""

    project = load_project_packages(project_root)
    lock = load_lock(project.root)
    if lock is None:
        raise PackageError(f"{LOCK_NAME} is missing; run 'ks pkg sync'")
    for name, spec in project.dependencies.items():
        entry = lock.packages.get(name)
        if entry is None or entry["source"] != spec.source():
            raise PackageError(
                f"dependency {name!r} in {MANIFEST_NAME} does not match {LOCK_NAME}; run 'ks pkg sync'"
            )
    reachable = set()
    pending = list(project.dependencies)
    while pending:
        name = pending.pop()
        if name not in reachable:
            reachable.add(name)
            pending.extend(lock.packages[name]["dependencies"])
    if reachable != set(lock.packages):
        raise PackageError(f"{LOCK_NAME} lists packages {MANIFEST_NAME} does not need; run 'ks pkg sync'")
    for name, entry in lock.packages.items():
        package_root = vendor_dir(project.root, name, entry["digest"])
        if not package_root.is_dir():
            raise PackageError(f"package {name!r} is not vendored; run 'ks pkg sync'")
        actual = tree_digest(package_root)
        if actual != entry["digest"]:
            raise PackageError(
                f"package {name!r} changed after it was locked (sha256 {actual[:16]}… "
                f"is not {entry['digest'][:16]}…); refusing to compile it"
            )
        if set(project.deny) & set(entry["surface"]):
            raise PackageError(f"package {name!r} is refused by [policy] deny")
    return PackageImportResolver(
        _vendor_root(project.root), lock, direct=project.dependencies, project_root=project.root
    )


def package_resolver_for(source: Path):
    """Return a verified resolver if ``source`` is in a project with dependencies."""

    from .modules import ModuleError

    project_root = _find_project_root(source.resolve(strict=False).parent)
    if project_root is None:
        return None
    try:
        data = _read_toml(project_root / MANIFEST_NAME)
    except PackageError:
        return None
    if not data.get("dependencies"):
        return None
    try:
        return verify_project(project_root)
    except PackageError as error:
        raise ModuleError(CODE, str(error), _ORIGIN) from error


def inspect_standalone(package_root: Path, name: str, *, registry_url: str) -> tuple[tuple[str, ...], str]:
    """Surface and digest of one package, with its registry dependencies fetched."""

    with tempfile.TemporaryDirectory(prefix="koschei-publish-") as directory:
        project = Path(directory)
        (project / MANIFEST_NAME).write_text(
            '[package]\nname = "publish-check"\nversion = "0.0.0"\n\n'
            f"[registry]\nurl = {json.dumps(registry_url)}\n\n"
            f"[dependencies]\n{name} = {{ path = {json.dumps(str(package_root))} }}\n",
            encoding="utf-8",
        )
        result = sync(project)
        entry = result.lock.packages[name]
        return tuple(entry["surface"]), entry["digest"]
