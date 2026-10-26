"""Deterministic identity manifests for locked Koschei native builds."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .mir import require_mir
from .module_lock import ModuleLock, verify_module_lock
from .modules import check_graph, load_graph

_SCHEMA = "koschei.native-build-manifest.v1"
_FIELDS = {
    "schema_version",
    "artifact_name",
    "artifact_size",
    "artifact_sha256",
    "module_lock_digest",
    "mir_version",
    "mir_fingerprint",
    "compiler_version",
    "backend",
    "backend_toolchain",
    "manifest_digest",
}


class BuildManifestError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class NativeBuildManifest:
    artifact_name: str
    artifact_size: int
    artifact_sha256: str
    module_lock_digest: str
    mir_version: str
    mir_fingerprint: str
    compiler_version: str
    backend: str
    backend_toolchain: str
    manifest_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA,
            "artifact_name": self.artifact_name,
            "artifact_size": self.artifact_size,
            "artifact_sha256": self.artifact_sha256,
            "module_lock_digest": self.module_lock_digest,
            "mir_version": self.mir_version,
            "mir_fingerprint": self.mir_fingerprint,
            "compiler_version": self.compiler_version,
            "backend": self.backend,
            "backend_toolchain": self.backend_toolchain,
            "manifest_digest": self.manifest_digest,
        }


def build_native_manifest(
    artifact: str | Path,
    *,
    module_lock_digest: str,
    mir_version: str,
    mir_fingerprint: str,
    backend_toolchain: str,
) -> NativeBuildManifest:
    path = Path(artifact)
    if not path.is_file():
        raise BuildManifestError("KS1910", f"native artifact is missing: {path}")
    if not _is_digest(module_lock_digest):
        raise BuildManifestError("KS1910", "module lock digest is invalid")
    if not _is_digest(mir_fingerprint):
        raise BuildManifestError("KS1910", "MIR fingerprint is invalid")
    if not backend_toolchain.strip():
        raise BuildManifestError("KS1910", "backend toolchain identity is empty")

    payload = {
        "schema_version": _SCHEMA,
        "artifact_name": path.name,
        "artifact_size": path.stat().st_size,
        "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "module_lock_digest": module_lock_digest,
        "mir_version": str(mir_version),
        "mir_fingerprint": mir_fingerprint,
        "compiler_version": __version__,
        "backend": "go-native",
        "backend_toolchain": backend_toolchain.strip(),
    }
    return NativeBuildManifest(
        artifact_name=str(payload["artifact_name"]),
        artifact_size=int(payload["artifact_size"]),
        artifact_sha256=str(payload["artifact_sha256"]),
        module_lock_digest=str(payload["module_lock_digest"]),
        mir_version=str(payload["mir_version"]),
        mir_fingerprint=str(payload["mir_fingerprint"]),
        compiler_version=str(payload["compiler_version"]),
        backend=str(payload["backend"]),
        backend_toolchain=str(payload["backend_toolchain"]),
        manifest_digest=_digest(payload),
    )


def load_native_manifest(path: str | Path) -> NativeBuildManifest:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise BuildManifestError("KS1912", "build manifest is not valid JSON") from error
    return _parse_manifest(payload)


def verify_native_manifest(
    manifest: NativeBuildManifest,
    artifact: str | Path,
    *,
    source: str | Path,
    locked: ModuleLock,
) -> NativeBuildManifest:
    verified = _parse_manifest(manifest.to_dict())
    artifact_path = Path(artifact)
    if not artifact_path.is_file():
        raise BuildManifestError("KS1913", f"native artifact is missing: {artifact_path}")
    if artifact_path.name != verified.artifact_name:
        raise BuildManifestError(
            "KS1913",
            f"artifact name changed: expected {verified.artifact_name}, "
            f"found {artifact_path.name}",
        )
    if artifact_path.stat().st_size != verified.artifact_size:
        raise BuildManifestError("KS1913", "native artifact size does not match manifest")
    artifact_digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    if artifact_digest != verified.artifact_sha256:
        raise BuildManifestError("KS1913", "native artifact digest does not match manifest")

    current_lock = verify_module_lock(source, locked)
    if current_lock.lock_digest != verified.module_lock_digest:
        raise BuildManifestError("KS1914", "module lock does not match build manifest")

    graph = load_graph(Path(source).resolve())
    check_graph(graph)
    mir = require_mir(graph)
    if str(mir.version) != verified.mir_version:
        raise BuildManifestError("KS1914", "MIR version does not match build manifest")
    if mir.fingerprint != verified.mir_fingerprint:
        raise BuildManifestError("KS1914", "MIR fingerprint does not match build manifest")
    return verified


def write_native_manifest(
    manifest: NativeBuildManifest,
    destination: str | Path,
) -> None:
    path = Path(destination)
    if path.exists():
        raise BuildManifestError(
            "KS1911",
            f"build manifest already exists: {path}",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _parse_manifest(payload: Any) -> NativeBuildManifest:
    if not isinstance(payload, dict):
        raise BuildManifestError("KS1912", "build manifest must be a JSON object")
    if set(payload) != _FIELDS:
        raise BuildManifestError("KS1912", "build manifest contains unsupported fields")
    if payload["schema_version"] != _SCHEMA:
        raise BuildManifestError("KS1912", "unsupported build manifest schema")

    artifact_name = _text(payload["artifact_name"], "artifact_name")
    if Path(artifact_name).name != artifact_name:
        raise BuildManifestError("KS1912", "artifact_name must be a file name")
    artifact_size = payload["artifact_size"]
    if isinstance(artifact_size, bool) or not isinstance(artifact_size, int):
        raise BuildManifestError("KS1912", "artifact_size must be an integer")
    if artifact_size < 0:
        raise BuildManifestError("KS1912", "artifact_size must not be negative")

    artifact_sha256 = _digest_field(payload["artifact_sha256"], "artifact_sha256")
    module_lock_digest = _digest_field(
        payload["module_lock_digest"],
        "module_lock_digest",
    )
    mir_fingerprint = _digest_field(payload["mir_fingerprint"], "mir_fingerprint")
    mir_version = _text(payload["mir_version"], "mir_version")
    compiler_version = _text(payload["compiler_version"], "compiler_version")
    backend = _text(payload["backend"], "backend")
    if backend != "go-native":
        raise BuildManifestError("KS1912", "unsupported native backend")
    backend_toolchain = _text(payload["backend_toolchain"], "backend_toolchain")
    manifest_digest = _digest_field(payload["manifest_digest"], "manifest_digest")

    unsigned = dict(payload)
    unsigned.pop("manifest_digest")
    if manifest_digest != _digest(unsigned):
        raise BuildManifestError("KS1912", "build manifest digest does not match contents")

    return NativeBuildManifest(
        artifact_name=artifact_name,
        artifact_size=artifact_size,
        artifact_sha256=artifact_sha256,
        module_lock_digest=module_lock_digest,
        mir_version=mir_version,
        mir_fingerprint=mir_fingerprint,
        compiler_version=compiler_version,
        backend=backend,
        backend_toolchain=backend_toolchain,
        manifest_digest=manifest_digest,
    )


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BuildManifestError("KS1912", f"{field} must be non-empty text")
    return value


def _digest_field(value: object, field: str) -> str:
    if not isinstance(value, str) or not _is_digest(value):
        raise BuildManifestError("KS1912", f"{field} must be a SHA-256 digest")
    return value


def _is_digest(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
