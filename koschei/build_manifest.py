"""Deterministic identity manifests for locked Koschei native builds."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import __version__

_SCHEMA = "koschei.native-build-manifest.v1"


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
        artifact_name=payload["artifact_name"],
        artifact_size=payload["artifact_size"],
        artifact_sha256=payload["artifact_sha256"],
        module_lock_digest=payload["module_lock_digest"],
        mir_version=payload["mir_version"],
        mir_fingerprint=payload["mir_fingerprint"],
        compiler_version=payload["compiler_version"],
        backend=payload["backend"],
        backend_toolchain=payload["backend_toolchain"],
        manifest_digest=_digest(payload),
    )


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
