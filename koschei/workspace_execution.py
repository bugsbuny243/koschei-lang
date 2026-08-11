"""Locked workspace package execution and native build support."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .codegen_go import generate_go_mir
from .interpreter import run_mir as interpret_mir
from .mir import require_mir
from .modules import ModuleGraph, check_graph
from .workspace import WorkspaceConfig, WorkspaceError, WorkspaceLock, load_workspace_lock
from .workspace_modules import load_workspace_member_graph
from .workspace_package_lock import verify_workspace_package_lock

WORKSPACE_BUILD_SCHEMA = "koschei.workspace-build.v1"
DEFAULT_WORKSPACE_LOCK = "koschei.workspace.lock.json"


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

    target = Path(output) if output is not None else workspace.root / "build" / package
    if not target.is_absolute():
        target = (Path.cwd() / target).resolve()
    else:
        target = target.resolve()
    manifest_path = Path(str(target) + ".workspace-build.json")
    if target.exists():
        raise WorkspaceError(f"workspace build artifact already exists: {target}")
    if manifest_path.exists():
        raise WorkspaceError(
            f"workspace build manifest already exists: {manifest_path}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=".koschei-workspace-build-",
        dir=target.parent,
    ) as temporary:
        directory = Path(temporary)
        staged = directory / "program"
        (directory / "main.go").write_text(go_source, encoding="utf-8")
        (directory / "go.mod").write_text(
            "module koscheiworkspaceprogram\n\ngo 1.21\n",
            encoding="utf-8",
        )
        completed = subprocess.run(
            [go_binary, "build", "-o", str(staged), "."],
            cwd=directory,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            details = completed.stderr.strip() or "unknown Go compiler error"
            raise WorkspaceError(
                "workspace native compilation failed; this is a Koschei compiler bug: "
                + details
            )
        try:
            os.link(staged, target)
        except FileExistsError:
            raise WorkspaceError(f"workspace build artifact already exists: {target}") from None
        except OSError as error:
            raise WorkspaceError(
                f"workspace build could not publish artifact without replacement: {error}"
            ) from error

    locked_member = next(
        member for member in program.locked.members if member.name == package
    )
    artifact_sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
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
    )


def verify_workspace_build(result: WorkspaceBuildResult) -> None:
    if not result.artifact.is_file() or not result.manifest.is_file():
        raise WorkspaceError("workspace build artifact or manifest is missing")
    try:
        payload = json.loads(result.manifest.read_text(encoding="utf-8"))
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
        return candidate.resolve(strict=False)
    return (workspace.root / candidate).resolve(strict=False)


def _write_create_only_json(path: Path, payload: dict[str, object]) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
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
