"""Parse-free freshness index for verified Koschei workspace locks.

A lock-index hit proves that the workspace/project manifests and every Koschei
source byte under workspace member roots are unchanged since a full package-lock
verification. It is an optimization only: the first identity miss still runs the
ordinary graph/semantic/module-lock verifier before an index can be published.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .workspace import WorkspaceConfig, WorkspaceError, WorkspaceLock
from .workspace_package_lock import verify_workspace_package_lock_full

LOCK_INDEX_SCHEMA = "koschei.workspace-lock-index.v1"
DEFAULT_LOCK_INDEX_DIR = ".koschei/cache/workspace-lock-index-v1"
MAX_INDEX_SOURCES = 2_000_000
MAX_INDEX_BYTES = 256 * 1024 * 1024
_DIGEST_LENGTH = 64


@dataclass(frozen=True, slots=True)
class IndexedSource:
    path: str
    sha256: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class WorkspaceSourceSnapshot:
    sources: tuple[IndexedSource, ...]

    def to_list(self) -> list[dict[str, str]]:
        return [source.to_dict() for source in self.sources]


def verify_or_create_lock_index(
    workspace: WorkspaceConfig,
    locked: WorkspaceLock,
    *,
    cache_root: str | Path,
) -> WorkspaceLock:
    """Verify a lock through its source index, or build the index after a full check."""

    root = _prepare_cache_root(Path(cache_root))
    entry = root / locked.workspace_digest
    if entry.exists() or entry.is_symlink():
        _verify_index_entry(workspace, locked, entry)
        return locked

    before = snapshot_workspace_sources(workspace)
    current = verify_workspace_package_lock_full(workspace, locked)
    after = snapshot_workspace_sources(workspace)
    if before != after:
        raise WorkspaceError(
            "workspace source bytes changed while the lock was being fully verified"
        )
    _verify_workspace_metadata(workspace, current)
    _publish_index(root, current, after)
    _verify_index_entry(workspace, current, root / current.workspace_digest)
    return current


def snapshot_workspace_sources(workspace: WorkspaceConfig) -> WorkspaceSourceSnapshot:
    observed: dict[str, str] = {}
    for member in workspace.members:
        member_root = member.project.root
        if member_root.is_symlink() or not member_root.is_dir():
            raise WorkspaceError(f"workspace member root is not a real directory: {member.path}")
        for directory, dirnames, filenames in os.walk(member_root, followlinks=False):
            base = Path(directory)
            for name in list(dirnames):
                child = base / name
                if child.is_symlink():
                    raise WorkspaceError(
                        f"workspace source tree contains a symlinked directory: {child}"
                    )
            for name in filenames:
                if not name.endswith(".ks"):
                    continue
                source = base / name
                if source.is_symlink() or not source.is_file():
                    raise WorkspaceError(
                        f"workspace source tree contains a non-regular .ks file: {source}"
                    )
                try:
                    relative = source.relative_to(workspace.root).as_posix()
                except ValueError as error:
                    raise WorkspaceError("workspace source escapes the workspace root") from error
                relative = _validate_source_path(relative)
                digest = _sha256_file(source)
                previous = observed.get(relative)
                if previous is not None and previous != digest:
                    raise WorkspaceError(f"workspace source identity is ambiguous: {relative}")
                observed[relative] = digest
                if len(observed) > MAX_INDEX_SOURCES:
                    raise WorkspaceError(
                        "workspace source count exceeds the 2000000-file lock-index budget"
                    )
    ordered = tuple(
        IndexedSource(path, observed[path]) for path in sorted(observed)
    )
    if not ordered:
        raise WorkspaceError("workspace lock index cannot represent an empty source tree")
    return WorkspaceSourceSnapshot(ordered)


def _verify_index_entry(
    workspace: WorkspaceConfig,
    locked: WorkspaceLock,
    entry: Path,
) -> None:
    if entry.is_symlink() or not entry.is_dir():
        raise WorkspaceError("workspace lock index entry is not a real directory")
    manifest = entry / "manifest.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise WorkspaceError("workspace lock index entry is incomplete")
    extras = sorted(path.name for path in entry.iterdir() if path.name != "manifest.json")
    if extras:
        raise WorkspaceError("workspace lock index entry contains unexpected files")
    try:
        raw = manifest.read_bytes()
        if len(raw) > MAX_INDEX_BYTES:
            raise WorkspaceError("workspace lock index exceeds the 256 MiB parsing budget")
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
    except WorkspaceError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise WorkspaceError("workspace lock index manifest is invalid") from error

    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "workspace_digest",
        "workspace_manifest_sha256",
        "source_count",
        "sources",
        "index_digest",
    }:
        raise WorkspaceError("workspace lock index contains unsupported fields")
    if payload["schema_version"] != LOCK_INDEX_SCHEMA:
        raise WorkspaceError("unsupported workspace lock index schema")
    if payload["workspace_digest"] != locked.workspace_digest:
        raise WorkspaceError("workspace lock index identity mismatch")
    if entry.name != locked.workspace_digest:
        raise WorkspaceError("workspace lock index directory key mismatch")
    if payload["workspace_manifest_sha256"] != locked.manifest_sha256:
        raise WorkspaceError("workspace lock index manifest identity mismatch")

    sources = _parse_sources(payload["sources"])
    if payload["source_count"] != len(sources):
        raise WorkspaceError("workspace lock index source_count mismatch")
    expected_digest = _digest(
        _index_payload(
            workspace_digest=locked.workspace_digest,
            workspace_manifest_sha256=locked.manifest_sha256,
            sources=sources,
        )
    )
    if not _is_digest(payload["index_digest"]) or payload["index_digest"] != expected_digest:
        raise WorkspaceError("workspace lock index digest mismatch")

    _verify_workspace_metadata(workspace, locked)
    current = snapshot_workspace_sources(workspace)
    if current.sources != sources:
        expected = {item.path: item.sha256 for item in sources}
        actual = {item.path: item.sha256 for item in current.sources}
        missing = sorted(set(expected) - set(actual))
        added = sorted(set(actual) - set(expected))
        changed = sorted(
            path for path in set(expected) & set(actual) if expected[path] != actual[path]
        )
        if missing:
            raise WorkspaceError("workspace lock index source missing: " + ", ".join(missing[:8]))
        if added:
            raise WorkspaceError("workspace lock index source set changed: " + ", ".join(added[:8]))
        if changed:
            raise WorkspaceError("workspace lock index source digest changed: " + ", ".join(changed[:8]))
        raise WorkspaceError("workspace lock index source inventory changed")


def _verify_workspace_metadata(workspace: WorkspaceConfig, locked: WorkspaceLock) -> None:
    if _sha256_file(workspace.manifest) != locked.manifest_sha256:
        raise WorkspaceError("workspace manifest digest changed")
    if workspace.build_order != locked.build_order:
        raise WorkspaceError("workspace dependency build order changed")
    if set(workspace.by_name) != {member.name for member in locked.members}:
        raise WorkspaceError("workspace member set changed")

    by_name = workspace.by_name
    for locked_member in locked.members:
        member = by_name[locked_member.name]
        entry = member.project.entry.relative_to(member.project.root).as_posix()
        if (
            member.path != locked_member.path
            or member.project.version != locked_member.version
            or entry != locked_member.entry
            or member.dependencies != locked_member.dependencies
            or _sha256_file(member.project.manifest) != locked_member.manifest_sha256
        ):
            raise WorkspaceError(
                f"workspace member identity changed: {locked_member.name}"
            )


def _publish_index(
    root: Path,
    locked: WorkspaceLock,
    snapshot: WorkspaceSourceSnapshot,
) -> None:
    entry = root / locked.workspace_digest
    sources = snapshot.sources
    payload_without_digest = _index_payload(
        workspace_digest=locked.workspace_digest,
        workspace_manifest_sha256=locked.manifest_sha256,
        sources=sources,
    )
    payload = dict(payload_without_digest)
    payload["index_digest"] = _digest(payload_without_digest)

    with tempfile.TemporaryDirectory(prefix=".lock-index-", dir=root) as temporary:
        stage = Path(temporary)
        _write_create_only_json(stage / "manifest.json", payload)
        _fsync_directory(stage)
        try:
            os.rename(stage, entry)
        except FileExistsError:
            return
        except OSError as error:
            if entry.exists() or entry.is_symlink():
                return
            raise WorkspaceError(f"workspace lock index publication failed: {error}") from error
        _fsync_directory(root)


def _index_payload(
    *,
    workspace_digest: str,
    workspace_manifest_sha256: str,
    sources: tuple[IndexedSource, ...],
) -> dict[str, object]:
    return {
        "schema_version": LOCK_INDEX_SCHEMA,
        "workspace_digest": workspace_digest,
        "workspace_manifest_sha256": workspace_manifest_sha256,
        "source_count": len(sources),
        "sources": [source.to_dict() for source in sources],
    }


def _parse_sources(value: Any) -> tuple[IndexedSource, ...]:
    if not isinstance(value, list) or not value:
        raise WorkspaceError("workspace lock index sources must be a non-empty array")
    if len(value) > MAX_INDEX_SOURCES:
        raise WorkspaceError("workspace lock index source count exceeds its budget")
    result: list[IndexedSource] = []
    for raw in value:
        if not isinstance(raw, dict) or set(raw) != {"path", "sha256"}:
            raise WorkspaceError("workspace lock index source has unsupported fields")
        path = _validate_source_path(raw["path"])
        if not _is_digest(raw["sha256"]):
            raise WorkspaceError(f"workspace lock index has invalid source digest: {path}")
        result.append(IndexedSource(path, raw["sha256"]))
    paths = [item.path for item in result]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise WorkspaceError("workspace lock index sources are not canonical")
    return tuple(result)


def _prepare_cache_root(requested: Path) -> Path:
    _reject_symlink_components(requested)
    root = requested.absolute()
    root.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(root)
    if root.is_symlink() or not root.is_dir():
        raise WorkspaceError("workspace lock index root is not a real directory")
    return root


def _reject_symlink_components(path: Path) -> None:
    absolute = path.absolute()
    parts = absolute.parts
    if not parts:
        return
    current = Path(parts[0])
    for part in parts[1:]:
        current = current / part
        if current.is_symlink():
            raise WorkspaceError(
                f"workspace lock index path contains a symlink component: {current}"
            )


def _validate_source_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise WorkspaceError("workspace lock index source path must be non-empty")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.suffix != ".ks":
        raise WorkspaceError(f"unsafe workspace lock index source path: {value}")
    return path.as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


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
        raise WorkspaceError(f"destination already exists: {path}") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
            raise WorkspaceError(f"duplicate workspace lock index JSON member: {key}")
        result[key] = value
    return result
