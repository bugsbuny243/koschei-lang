"""Locked workspace package execution and native build support."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .codegen_go import generate_go_mir
from .interpreter import run_mir as interpret_mir
from .mir import require_mir
from .modules import ModuleGraph, check_graph
from .workspace import WorkspaceConfig, WorkspaceError, WorkspaceLock, load_workspace_lock
from .workspace_cache import (
    DEFAULT_CACHE_DIR,
    WorkspaceCacheIdentity,
    build_or_load_cached_native,
    detect_go_toolchain,
    publish_cached_artifact,
)
from .workspace_modules import load_workspace_member_graph
from .workspace_package_lock import verify_workspace_package_lock

WORKSPACE_BUILD_SCHEMA = "koschei.workspace-build.v1"
DEFAULT_WORKSPACE_LOCK = "koschei.workspace.lock.json"
_DIGEST_LENGTH = 64


@dataclass(frozen=True, slots=True)
class LockedWorkspaceProgram:
    workspace: WorkspaceConfig
    locked: WorkspaceLock
    package: str
    graph: ModuleGraph


@dataclass(frozen=True, slots=True)
class WorkspaceBuildResult:
    package: str
    artifact: Path
    manifest: Path
    artifact_sha256: str
    workspace_digest: str
    module_lock_digest: str
    mir_fingerprint: str
    cache_key: str
    cache_hit: bool


def prepare_locked_workspace_program(
    workspace: WorkspaceConfig,
    package: str,
    *,
    lock_path: str | Path | None = None,
) -> LockedWorkspaceProgram:
    member = workspace.by_name.get(package)
    if member is None:
        raise WorkspaceError(f"unknown workspace package: {package}")

    lockfile = _resolve_lock_path(workspace, lock_path)
    if lockfile.is_symlink():
        raise WorkspaceError("workspace execution lock cannot be a symlink")
    if not lockfile.is_file():
        raise WorkspaceError(
            f"workspace execution requires a verified lock: {lockfile}"
        )

    locked = load_workspace_lock(lockfile)
    verified = verify_workspace_package_lock(workspace, locked)
    if not any(candidate.name == package for candidate in verified.members):
        raise WorkspaceError(f"package is missing from workspace lock: {package}")

    graph = load_workspace_member_graph(workspace, package)
    check_graph(graph)
    return LockedWorkspaceProgram(
        workspace=workspace,
        locked=verified,
        package=package,
        graph=graph,
    )


def run_locked_workspace_package(
    workspace: WorkspaceConfig,
    package: str,
    *,
    lock_path: str | Path | None = None,
) -> int:
    program = prepare_locked_workspace_program(
        workspace,
        package,
        lock_path=lock_path,
    )
    return interpret_mir(require_mir(program.graph), [])


def build_locked_workspace_package(
    workspace: WorkspaceConfig,
    package: str,
    *,
    output: str | Path | None = None,
    lock_path: str | Path | None = None,
    cache_dir: str | Path | None = None,
) -> WorkspaceBuildResult:
    program = prepare_locked_workspace_program(
        workspace,
        package,
        lock_path=lock_path,
    )
    mir = require_mir(program.graph)
    go_source = generate_go_mir(mir)

    go_binary = shutil.which("go")
    if go_binary is None:
        raise WorkspaceError(
            "'go' was not found; install Go for native workspace builds"
        )
    toolchain, go_environment = detect_go_toolchain(go_binary)
    locked_member = next(
        member for member in program.locked.members if member.name == package
    )
    identity = WorkspaceCacheIdentity(
        package=package,
        workspace_digest=program.locked.workspace_digest,
        module_lock_digest=locked_member.module_lock_digest,
        mir_version=mir.version,
        mir_fingerprint=mir.fingerprint,
        go_source_sha256=hashlib.sha256(go_source.encode("utf-8")).hexdigest(),
        toolchain=toolchain,
    )
    cache_root = _resolve_cache_path(workspace, cache_dir)
    cached = build_or_load_cached_native(
        cache_root=cache_root,
        identity=identity,
        go_binary=go_binary,
        go_source=go_source,
        go_environment=go_environment,
    )

    raw_target = Path(output) if output is not None else workspace.root / "build" / package
    if raw_target.is_symlink():
        raise WorkspaceError("workspace build artifact target cannot be a symlink")
    target = raw_target.absolute()
    manifest_path = Path(str(target) + ".workspace-build.json")
    if target.exists():
        raise WorkspaceError(f"workspace build artifact already exists: {target}")
    if manifest_path.exists() or manifest_path.is_symlink():
        raise WorkspaceError(
            f"workspace build manifest already exists: {manifest_path}"
        )

    publish_cached_artifact(cached.artifact, target)
    artifact_sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
    if artifact_sha256 != cached.artifact_sha256:
        target.unlink(missing_ok=True)
        raise WorkspaceError("published workspace artifact differs from verified cache")

    payload = {
        "schema_version": WORKSPACE_BUILD_SCHEMA,
        "package": package,
        "artifact": target.name,
        "artifact_sha256": artifact_sha256,
        "workspace_digest": program.locked.workspace_digest,
        "workspace_manifest_sha256": program.locked.manifest_sha256,
        "module_lock_digest": locked_member.module_lock_digest,
        "mir_version": mir.version,
        "mir_fingerprint": mir.fingerprint,
    }
    try:
        _write_create_only_json(manifest_path, payload)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return WorkspaceBuildResult(
        package=package,
        artifact=target,
        manifest=manifest_path,
        artifact_sha256=artifact_sha256,
        workspace_digest=program.locked.workspace_digest,
        module_lock_digest=locked_member.module_lock_digest,
        mir_fingerprint=mir.fingerprint,
        cache_key=cached.cache_key,
        cache_hit=cached.hit,
    )


def verify_workspace_build(result: WorkspaceBuildResult) -> None:
    if not result.artifact.is_file() or not result.manifest.is_file():
        raise WorkspaceError("workspace build artifact or manifest is missing")
    try:
        payload = json.loads(
            result.manifest.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_pairs,
        )
    except WorkspaceError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise WorkspaceError("workspace build manifest is not valid UTF-8 JSON") from error
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "package",
        "artifact",
        "artifact_sha256",
        "workspace_digest",
        "workspace_manifest_sha256",
        "module_lock_digest",
        "mir_version",
        "mir_fingerprint",
    }:
        raise WorkspaceError("workspace build manifest contains unsupported fields")
    if payload["schema_version"] != WORKSPACE_BUILD_SCHEMA:
        raise WorkspaceError("unsupported workspace build manifest schema")
    if payload["package"] != result.package:
        raise WorkspaceError("workspace build manifest package mismatch")
    if payload["artifact"] != result.artifact.name:
        raise WorkspaceError("workspace build manifest artifact name mismatch")
    for field in (
        "artifact_sha256",
        "workspace_digest",
        "workspace_manifest_sha256",
        "module_lock_digest",
        "mir_fingerprint",
    ):
        if not _is_digest(payload[field]):
            raise WorkspaceError(f"workspace build manifest has invalid {field}")
    if not isinstance(payload["mir_version"], int) or isinstance(payload["mir_version"], bool):
        raise WorkspaceError("workspace build manifest has invalid mir_version")

    observed = hashlib.sha256(result.artifact.read_bytes()).hexdigest()
    if observed != payload["artifact_sha256"] or observed != result.artifact_sha256:
        raise WorkspaceError("workspace build artifact digest mismatch")
    if payload["workspace_digest"] != result.workspace_digest:
        raise WorkspaceError("workspace build digest does not match locked workspace")
    if payload["module_lock_digest"] != result.module_lock_digest:
        raise WorkspaceError("workspace build module lock digest mismatch")
    if payload["mir_fingerprint"] != result.mir_fingerprint:
        raise WorkspaceError("workspace build MIR fingerprint mismatch")


def _resolve_lock_path(
    workspace: WorkspaceConfig,
    lock_path: str | Path | None,
) -> Path:
    if lock_path is None:
        return workspace.root / DEFAULT_WORKSPACE_LOCK
    candidate = Path(lock_path)
    if candidate.is_absolute():
        return candidate
    _validate_relative_control_path(candidate, "workspace lock")
    return workspace.root / candidate


def _resolve_cache_path(
    workspace: WorkspaceConfig,
    cache_dir: str | Path | None,
) -> Path:
    if cache_dir is None:
        return workspace.root / DEFAULT_CACHE_DIR
    candidate = Path(cache_dir)
    if candidate.is_absolute():
        return candidate
    _validate_relative_control_path(candidate, "workspace cache")
    return workspace.root / candidate


def _validate_relative_control_path(path: Path, label: str) -> None:
    pure = PurePosixPath(path.as_posix())
    if pure.is_absolute() or ".." in pure.parts or path.as_posix().startswith("~"):
        raise WorkspaceError(f"{label} path must stay within the workspace root")


def _write_create_only_json(path: Path, payload: dict[str, object]) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        raise WorkspaceError(f"workspace build manifest already exists: {path}") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _is_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _DIGEST_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WorkspaceError(f"duplicate workspace build JSON member: {key}")
        result[key] = value
    return result
