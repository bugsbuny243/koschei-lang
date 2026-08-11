"""Immutable compiler-analysis cache for locked workspace package builds.

The cache stores only deterministic backend input produced after a successful
Koschei semantic/MIR pipeline. It never deserializes Python objects or executable
cache payloads. A hit is accepted only when the selected package source identity,
package manifest, and compiler implementation contract are unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .workspace import WorkspaceError

ANALYSIS_CACHE_SCHEMA = "koschei.workspace-analysis-cache.v1"
ANALYSIS_CACHE_KEY_SCHEMA = "koschei.workspace-analysis-cache-key.v1"
COMPILER_CONTRACT_SCHEMA = "koschei.compiler-contract.v1"
DEFAULT_ANALYSIS_CACHE_DIR = ".koschei/cache/workspace-analysis-v1"
_DIGEST_LENGTH = 64


@dataclass(frozen=True, slots=True)
class WorkspaceAnalysisIdentity:
    package: str
    member_manifest_sha256: str
    module_lock_digest: str
    compiler_contract_digest: str

    def key_payload(self) -> dict[str, object]:
        return {
            "schema_version": ANALYSIS_CACHE_KEY_SCHEMA,
            "package": self.package,
            "member_manifest_sha256": self.member_manifest_sha256,
            "module_lock_digest": self.module_lock_digest,
            "compiler_contract_digest": self.compiler_contract_digest,
        }

    @property
    def cache_key(self) -> str:
        return _digest(self.key_payload())


@dataclass(frozen=True, slots=True)
class WorkspaceAnalysisResult:
    go_source: str
    mir_version: int
    mir_fingerprint: str
    go_source_sha256: str
    cache_key: str
    hit: bool


def compiler_contract_digest() -> str:
    """Hash the installed Koschei Python implementation conservatively.

    Hashing every package Python source is intentionally broader than the exact
    parser/type/MIR/codegen dependency set. A compiler implementation change may
    cost a cache miss, but it cannot silently reuse analysis produced by different
    compiler code.
    """

    package_root = Path(__file__).parent
    if package_root.is_symlink():
        raise WorkspaceError("Koschei compiler package root cannot be a symlink")

    files: list[dict[str, str]] = []
    for path in sorted(package_root.rglob("*.py"), key=lambda item: item.as_posix()):
        if path.is_symlink() or not path.is_file():
            raise WorkspaceError("Koschei compiler contract contains a symlinked source")
        relative = path.relative_to(package_root).as_posix()
        files.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    if not files:
        raise WorkspaceError("Koschei compiler contract has no Python sources")

    payload = {
        "schema_version": COMPILER_CONTRACT_SCHEMA,
        "python_implementation": sys.implementation.name,
        "python_version": list(sys.version_info[:3]),
        "files": files,
    }
    return _digest(payload)


def load_or_build_analysis(
    *,
    cache_root: str | Path,
    identity: WorkspaceAnalysisIdentity,
    builder: Callable[[], tuple[str, int, str]],
) -> WorkspaceAnalysisResult:
    requested_root = Path(cache_root)
    if requested_root.is_symlink():
        raise WorkspaceError("workspace analysis cache root cannot be a symlink")
    root = requested_root.resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)

    entry = root / identity.cache_key
    if entry.exists() or entry.is_symlink():
        return _load_entry(entry, identity, hit=True)

    go_source, mir_version, mir_fingerprint = builder()
    if not isinstance(go_source, str):
        raise WorkspaceError("workspace analysis builder returned invalid backend source")
    if not isinstance(mir_version, int) or isinstance(mir_version, bool) or mir_version < 1:
        raise WorkspaceError("workspace analysis builder returned invalid MIR version")
    if not _is_digest(mir_fingerprint):
        raise WorkspaceError("workspace analysis builder returned invalid MIR fingerprint")

    encoded_go = go_source.encode("utf-8")
    go_source_sha256 = hashlib.sha256(encoded_go).hexdigest()
    manifest_payload = {
        "schema_version": ANALYSIS_CACHE_SCHEMA,
        "cache_key": identity.cache_key,
        "identity": identity.key_payload(),
        "backend": "main.go",
        "go_source_sha256": go_source_sha256,
        "mir_version": mir_version,
        "mir_fingerprint": mir_fingerprint,
    }

    with tempfile.TemporaryDirectory(prefix=".analysis-", dir=root) as temporary:
        stage = Path(temporary)
        _write_create_only_bytes(stage / "main.go", encoded_go, mode=0o644)
        _write_create_only_json(stage / "manifest.json", manifest_payload)
        _fsync_directory(stage)

        try:
            os.rename(stage, entry)
        except FileExistsError:
            return _load_entry(entry, identity, hit=True)
        except OSError as error:
            if entry.exists() or entry.is_symlink():
                return _load_entry(entry, identity, hit=True)
            raise WorkspaceError(
                f"workspace analysis cache publication failed: {error}"
            ) from error
        _fsync_directory(root)

    return _load_entry(entry, identity, hit=False)


def _load_entry(
    entry: Path,
    identity: WorkspaceAnalysisIdentity,
    *,
    hit: bool,
) -> WorkspaceAnalysisResult:
    if entry.is_symlink() or not entry.is_dir():
        raise WorkspaceError("workspace analysis cache entry is not a real directory")
    manifest = entry / "manifest.json"
    backend = entry / "main.go"
    if manifest.is_symlink() or backend.is_symlink():
        raise WorkspaceError("workspace analysis cache entry contains a symlink")
    if not manifest.is_file() or not backend.is_file():
        raise WorkspaceError("workspace analysis cache entry is incomplete")
    extras = sorted(
        path.name
        for path in entry.iterdir()
        if path.name not in {"manifest.json", "main.go"}
    )
    if extras:
        raise WorkspaceError("workspace analysis cache entry contains unexpected files")

    try:
        payload = json.loads(
            manifest.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_pairs,
        )
    except WorkspaceError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise WorkspaceError("workspace analysis cache manifest is invalid") from error

    expected_fields = {
        "schema_version",
        "cache_key",
        "identity",
        "backend",
        "go_source_sha256",
        "mir_version",
        "mir_fingerprint",
    }
    if not isinstance(payload, dict) or set(payload) != expected_fields:
        raise WorkspaceError("workspace analysis cache manifest has unsupported fields")
    if payload["schema_version"] != ANALYSIS_CACHE_SCHEMA:
        raise WorkspaceError("unsupported workspace analysis cache schema")
    if payload["identity"] != identity.key_payload():
        raise WorkspaceError("workspace analysis cache identity mismatch")
    if payload["cache_key"] != identity.cache_key or entry.name != identity.cache_key:
        raise WorkspaceError("workspace analysis cache key mismatch")
    if payload["backend"] != "main.go":
        raise WorkspaceError("workspace analysis cache backend name mismatch")
    if not _is_digest(payload["go_source_sha256"]):
        raise WorkspaceError("workspace analysis cache backend digest is invalid")
    if not isinstance(payload["mir_version"], int) or isinstance(payload["mir_version"], bool):
        raise WorkspaceError("workspace analysis cache MIR version is invalid")
    if payload["mir_version"] < 1:
        raise WorkspaceError("workspace analysis cache MIR version is invalid")
    if not _is_digest(payload["mir_fingerprint"]):
        raise WorkspaceError("workspace analysis cache MIR fingerprint is invalid")

    try:
        encoded_go = backend.read_bytes()
        go_source = encoded_go.decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise WorkspaceError("workspace analysis cache backend source is invalid") from error
    observed = hashlib.sha256(encoded_go).hexdigest()
    if observed != payload["go_source_sha256"]:
        raise WorkspaceError("workspace analysis cache backend digest mismatch")

    return WorkspaceAnalysisResult(
        go_source=go_source,
        mir_version=payload["mir_version"],
        mir_fingerprint=payload["mir_fingerprint"],
        go_source_sha256=observed,
        cache_key=identity.cache_key,
        hit=hit,
    )


def _write_create_only_bytes(path: Path, content: bytes, *, mode: int) -> None:
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        raise WorkspaceError(f"destination already exists: {path}") from None
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _write_create_only_json(path: Path, payload: dict[str, object]) -> None:
    _write_create_only_bytes(
        path,
        (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        mode=0o644,
    )


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
            raise WorkspaceError(f"duplicate workspace analysis cache JSON member: {key}")
        result[key] = value
    return result
