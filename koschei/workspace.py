"""Fail-closed Koschei workspace/monorepo support.

Workspace v1 composes existing Koschei projects without weakening their project,
module, or capability boundaries. Dependency edges are explicit orchestration
metadata; source-level cross-package imports are deliberately not invented here.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import os
import tempfile
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .module_lock import build_module_lock
from .project import (
    MANIFEST_NAME,
    PACKAGE_NAME,
    SEMVER,
    ProjectConfig,
    ProjectError,
    load_project,
)

WORKSPACE_MANIFEST_NAME = "koschei.workspace.toml"
WORKSPACE_SCHEMA = "koschei.workspace/v1"
WORKSPACE_LOCK_SCHEMA = "koschei.workspace-lock.v1"
MAX_WORKSPACE_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_WORKSPACE_MEMBERS = 100_000
MAX_WORKSPACE_DEPENDENCY_EDGES = 1_000_000
_DIGEST_LENGTH = 64


class WorkspaceError(ValueError):
    """A workspace manifest, dependency graph, or lock is invalid."""


@dataclass(frozen=True, slots=True)
class WorkspaceMember:
    path: str
    project: ProjectConfig
    dependencies: tuple[str, ...]

    @property
    def name(self) -> str:
        return self.project.name


@dataclass(frozen=True, slots=True)
class WorkspaceConfig:
    root: Path
    manifest: Path
    members: tuple[WorkspaceMember, ...]
    build_order: tuple[str, ...]

    @property
    def by_name(self) -> dict[str, WorkspaceMember]:
        return {member.name: member for member in self.members}


@dataclass(frozen=True, slots=True)
class WorkspaceLockedMember:
    name: str
    path: str
    version: str
    entry: str
    dependencies: tuple[str, ...]
    manifest_sha256: str
    module_lock_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "path": self.path,
            "version": self.version,
            "entry": self.entry,
            "dependencies": list(self.dependencies),
            "manifest_sha256": self.manifest_sha256,
            "module_lock_digest": self.module_lock_digest,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceLock:
    manifest_sha256: str
    members: tuple[WorkspaceLockedMember, ...]
    build_order: tuple[str, ...]
    workspace_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": WORKSPACE_LOCK_SCHEMA,
            "manifest_sha256": self.manifest_sha256,
            "members": [member.to_dict() for member in self.members],
            "build_order": list(self.build_order),
            "workspace_digest": self.workspace_digest,
        }


def load_workspace(path: str | Path) -> WorkspaceConfig:
    requested = Path(path)
    manifest = (
        requested
        if requested.name == WORKSPACE_MANIFEST_NAME
        else requested / WORKSPACE_MANIFEST_NAME
    )
    if manifest.is_symlink():
        raise WorkspaceError("workspace manifest cannot be a symlink")
    manifest = manifest.resolve()
    if not manifest.is_file():
        raise WorkspaceError(f"Workspace manifest not found: {manifest}")

    try:
        raw_manifest = manifest.read_bytes()
        if len(raw_manifest) > MAX_WORKSPACE_MANIFEST_BYTES:
            raise WorkspaceError("workspace manifest exceeds the 8 MiB parsing budget")
        manifest_text = raw_manifest.decode("utf-8")
        data: dict[str, Any] = tomllib.loads(manifest_text)
    except WorkspaceError:
        raise
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise WorkspaceError(f"Invalid {WORKSPACE_MANIFEST_NAME}: {error}") from error

    if set(data) != {"schema_version", "workspace", "dependencies"}:
        raise WorkspaceError(
            f"{WORKSPACE_MANIFEST_NAME} must contain only schema_version, "
            "[workspace], and [dependencies]"
        )
    if data["schema_version"] != WORKSPACE_SCHEMA:
        raise WorkspaceError(f"unsupported workspace schema: {data['schema_version']!r}")
    workspace_table = data["workspace"]
    dependency_table = data["dependencies"]
    if not isinstance(workspace_table, dict) or set(workspace_table) != {"members"}:
        raise WorkspaceError("[workspace] must contain exactly members")
    if not isinstance(dependency_table, dict):
        raise WorkspaceError("[dependencies] must be a table")

    raw_members = workspace_table["members"]
    if not isinstance(raw_members, list) or not raw_members:
        raise WorkspaceError("workspace.members must be a non-empty array")
    if len(raw_members) > MAX_WORKSPACE_MEMBERS:
        raise WorkspaceError("workspace member count exceeds the 100000-member budget")
    if any(not isinstance(item, str) for item in raw_members):
        raise WorkspaceError("workspace.members entries must be strings")

    root = manifest.parent.resolve()
    normalized_paths = tuple(_validate_member_path(item) for item in raw_members)
    if len(normalized_paths) != len(set(normalized_paths)):
        raise WorkspaceError("workspace.members contains duplicate paths")

    projects: list[tuple[str, ProjectConfig]] = []
    for relative in normalized_paths:
        member_root = _safe_member_directory(root, relative)
        member_manifest = member_root / MANIFEST_NAME
        if member_manifest.is_symlink():
            raise WorkspaceError(f"workspace member manifest cannot be a symlink: {relative}")
        try:
            project = load_project(member_root)
        except ProjectError as error:
            raise WorkspaceError(f"invalid workspace member {relative}: {error}") from error
        if project.root != member_root.resolve():
            raise WorkspaceError(f"workspace member root changed during resolution: {relative}")
        projects.append((relative, project))

    names = [project.name for _, project in projects]
    duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
    if duplicates:
        raise WorkspaceError("duplicate workspace package names: " + ", ".join(duplicates))
    known = set(names)

    normalized_dependencies: dict[str, tuple[str, ...]] = {name: () for name in names}
    edge_count = 0
    for owner, raw in dependency_table.items():
        if not isinstance(owner, str) or not PACKAGE_NAME.fullmatch(owner):
            raise WorkspaceError(f"invalid dependency owner package name: {owner!r}")
        if owner not in known:
            raise WorkspaceError(f"dependencies declared for unknown package: {owner}")
        if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
            raise WorkspaceError(f"dependencies.{owner} must be an array of package names")
        if len(raw) != len(set(raw)):
            raise WorkspaceError(f"dependencies.{owner} contains duplicates")
        edge_count += len(raw)
        if edge_count > MAX_WORKSPACE_DEPENDENCY_EDGES:
            raise WorkspaceError(
                "workspace dependency count exceeds the 1000000-edge budget"
            )
        for dependency in raw:
            if dependency not in known:
                raise WorkspaceError(f"{owner} depends on unknown workspace package: {dependency}")
            if dependency == owner:
                raise WorkspaceError(f"{owner} cannot depend on itself")
        normalized_dependencies[owner] = tuple(sorted(raw))

    build_order = _topological_order(normalized_dependencies)
    members = tuple(
        WorkspaceMember(
            path=relative,
            project=project,
            dependencies=normalized_dependencies[project.name],
        )
        for relative, project in sorted(projects, key=lambda item: item[1].name)
    )
    return WorkspaceConfig(
        root=root,
        manifest=manifest,
        members=members,
        build_order=build_order,
    )


def build_workspace_lock(workspace: WorkspaceConfig) -> WorkspaceLock:
    locked: list[WorkspaceLockedMember] = []
    by_name = workspace.by_name
    for name in workspace.build_order:
        member = by_name[name]
        module_lock = build_module_lock(member.project.entry)
        entry = member.project.entry.relative_to(member.project.root).as_posix()
        locked.append(
            WorkspaceLockedMember(
                name=name,
                path=member.path,
                version=member.project.version,
                entry=entry,
                dependencies=member.dependencies,
                manifest_sha256=_sha256_file(member.project.manifest),
                module_lock_digest=module_lock.lock_digest,
            )
        )

    ordered_members = tuple(locked)
    manifest_sha256 = _sha256_file(workspace.manifest)
    payload = _workspace_lock_payload(
        manifest_sha256=manifest_sha256,
        members=ordered_members,
        build_order=workspace.build_order,
    )
    return WorkspaceLock(
        manifest_sha256=manifest_sha256,
        members=ordered_members,
        build_order=workspace.build_order,
        workspace_digest=_digest(payload),
    )


def load_workspace_lock(path: str | Path) -> WorkspaceLock:
    lock_path = Path(path)
    try:
        text = lock_path.read_text(encoding="utf-8")
        payload = json.loads(text, object_pairs_hook=_unique_pairs)
    except WorkspaceError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise WorkspaceError("workspace lock is not valid UTF-8 JSON") from error
    return _parse_workspace_lock(payload)


def verify_workspace_lock(
    workspace: WorkspaceConfig,
    locked: WorkspaceLock,
) -> WorkspaceLock:
    current = build_workspace_lock(workspace)
    if current.to_dict() != locked.to_dict():
        if current.manifest_sha256 != locked.manifest_sha256:
            raise WorkspaceError("workspace manifest digest changed")
        expected = {member.name: member for member in locked.members}
        actual = {member.name: member for member in current.members}
        if set(expected) != set(actual):
            raise WorkspaceError("workspace member set changed")
        for name in current.build_order:
            if expected[name] != actual[name]:
                raise WorkspaceError(f"workspace member identity changed: {name}")
        if current.build_order != locked.build_order:
            raise WorkspaceError("workspace dependency build order changed")
        raise WorkspaceError("workspace lock digest changed")
    return current


def write_workspace_lock(
    lock: WorkspaceLock,
    path: str | Path,
    *,
    replace: bool = False,
) -> None:
    destination = Path(path)
    if destination.exists() and not replace:
        raise WorkspaceError(
            f"workspace lock already exists: {destination}; use --force to replace it"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(lock.to_dict(), indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        dir=destination.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _parse_workspace_lock(payload: Any) -> WorkspaceLock:
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "manifest_sha256",
        "members",
        "build_order",
        "workspace_digest",
    }:
        raise WorkspaceError("workspace lock contains missing or unknown fields")
    if payload["schema_version"] != WORKSPACE_LOCK_SCHEMA:
        raise WorkspaceError("unsupported workspace lock schema")
    manifest_sha256 = payload["manifest_sha256"]
    workspace_digest = payload["workspace_digest"]
    if not _is_digest(manifest_sha256) or not _is_digest(workspace_digest):
        raise WorkspaceError("workspace lock contains an invalid SHA-256 digest")

    raw_members = payload["members"]
    raw_order = payload["build_order"]
    if not isinstance(raw_members, list) or not raw_members:
        raise WorkspaceError("workspace lock members must be a non-empty array")
    if not isinstance(raw_order, list) or any(not isinstance(item, str) for item in raw_order):
        raise WorkspaceError("workspace lock build_order must be an array of package names")
    if len(raw_order) != len(set(raw_order)):
        raise WorkspaceError("workspace lock build_order contains duplicates")

    members: list[WorkspaceLockedMember] = []
    for raw in raw_members:
        if not isinstance(raw, dict) or set(raw) != {
            "name",
            "path",
            "version",
            "entry",
            "dependencies",
            "manifest_sha256",
            "module_lock_digest",
        }:
            raise WorkspaceError("workspace locked member contains missing or unknown fields")
        name = raw["name"]
        if not isinstance(name, str) or not PACKAGE_NAME.fullmatch(name):
            raise WorkspaceError("workspace lock contains an invalid package name")
        path = _validate_member_path(raw["path"])
        entry = _validate_entry_path(raw["entry"])
        version = raw["version"]
        dependencies = raw["dependencies"]
        if not isinstance(version, str) or not SEMVER.fullmatch(version):
            raise WorkspaceError(f"workspace lock version is invalid for {name}")
        if not isinstance(dependencies, list) or any(
            not isinstance(item, str) for item in dependencies
        ):
            raise WorkspaceError(f"workspace lock dependencies are invalid for {name}")
        if dependencies != sorted(dependencies) or len(dependencies) != len(set(dependencies)):
            raise WorkspaceError(f"workspace lock dependencies are not canonical for {name}")
        if not _is_digest(raw["manifest_sha256"]) or not _is_digest(
            raw["module_lock_digest"]
        ):
            raise WorkspaceError(f"workspace lock digest is invalid for {name}")
        members.append(
            WorkspaceLockedMember(
                name=name,
                path=path,
                version=version,
                entry=entry,
                dependencies=tuple(dependencies),
                manifest_sha256=raw["manifest_sha256"],
                module_lock_digest=raw["module_lock_digest"],
            )
        )

    names = [member.name for member in members]
    if len(names) != len(set(names)) or set(names) != set(raw_order):
        raise WorkspaceError("workspace lock member/build_order package sets differ")
    dependencies = {member.name: member.dependencies for member in members}
    if _topological_order(dependencies) != tuple(raw_order):
        raise WorkspaceError("workspace lock build_order does not match dependency graph")
    if [member.name for member in members] != raw_order:
        raise WorkspaceError("workspace lock members must be stored in build order")

    ordered = tuple(members)
    expected = _digest(
        _workspace_lock_payload(
            manifest_sha256=manifest_sha256,
            members=ordered,
            build_order=tuple(raw_order),
        )
    )
    if workspace_digest != expected:
        raise WorkspaceError("workspace lock digest does not match its payload")
    return WorkspaceLock(
        manifest_sha256=manifest_sha256,
        members=ordered,
        build_order=tuple(raw_order),
        workspace_digest=workspace_digest,
    )


def _workspace_lock_payload(
    *,
    manifest_sha256: str,
    members: tuple[WorkspaceLockedMember, ...],
    build_order: tuple[str, ...],
) -> dict[str, object]:
    return {
        "schema_version": WORKSPACE_LOCK_SCHEMA,
        "manifest_sha256": manifest_sha256,
        "members": [member.to_dict() for member in members],
        "build_order": list(build_order),
    }


def _topological_order(dependencies: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    known = set(dependencies)
    dependents: dict[str, list[str]] = {name: [] for name in dependencies}
    indegree: dict[str, int] = {}
    edge_count = 0
    for owner, required in dependencies.items():
        unknown = sorted(set(required) - known)
        if unknown:
            raise WorkspaceError(
                f"{owner} depends on unknown workspace packages: {', '.join(unknown)}"
            )
        indegree[owner] = len(required)
        edge_count += len(required)
        if edge_count > MAX_WORKSPACE_DEPENDENCY_EDGES:
            raise WorkspaceError(
                "workspace dependency count exceeds the 1000000-edge budget"
            )
        for dependency in required:
            dependents[dependency].append(owner)

    for dependency in dependents:
        dependents[dependency].sort()
    ready = [name for name, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        name = heapq.heappop(ready)
        order.append(name)
        for candidate in dependents[name]:
            indegree[candidate] -= 1
            if indegree[candidate] == 0:
                heapq.heappush(ready, candidate)
    if len(order) != len(dependencies):
        cyclic = sorted(name for name, count in indegree.items() if count > 0)
        raise WorkspaceError("workspace dependency cycle detected: " + ", ".join(cyclic))
    return tuple(order)


def _safe_member_directory(root: Path, relative: str) -> Path:
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            raise WorkspaceError(f"workspace member path contains a symlink: {relative}")
    resolved = current.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise WorkspaceError(f"workspace member escapes the workspace root: {relative}") from error
    if not resolved.is_dir():
        raise WorkspaceError(f"workspace member directory not found: {relative}")
    return resolved


def _validate_member_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("~"):
        raise WorkspaceError(f"unsafe workspace member path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() in {"", "."}:
        raise WorkspaceError(f"unsafe workspace member path: {value!r}")
    return path.as_posix()


def _validate_entry_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("~"):
        raise WorkspaceError("unsafe workspace member entry path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.suffix != ".ks":
        raise WorkspaceError("unsafe workspace member entry path")
    return path.as_posix()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _DIGEST_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WorkspaceError(f"duplicate workspace lock JSON member: {key}")
        result[key] = value
    return result
