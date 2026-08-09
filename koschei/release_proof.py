"""Seal a byte-reproducible Koschei native release candidate into one proof."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .build_manifest import NativeBuildManifest
from .reproducibility import ReproducibilityReport, verify_reproducibility_report

_SCHEMA = "koschei.release-proof.v1"
_FIELDS = {
    "schema_version",
    "state",
    "authority",
    "module_lock_digest",
    "mir_version",
    "mir_fingerprint",
    "compiler_version",
    "backend",
    "backend_toolchain",
    "release_manifest_digest",
    "witness_manifest_digest",
    "release_artifact_sha256",
    "witness_artifact_sha256",
    "reproducibility_report_digest",
    "shared_input_digest",
    "byte_reproducible",
    "owner_approval_required",
    "automatic_publish_allowed",
    "package_registry_write_allowed",
    "production_integration_allowed",
    "proof_digest",
}


class ReleaseProofError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class ReleaseProof:
    state: str
    authority: str
    module_lock_digest: str
    mir_version: str
    mir_fingerprint: str
    compiler_version: str
    backend: str
    backend_toolchain: str
    release_manifest_digest: str
    witness_manifest_digest: str
    release_artifact_sha256: str
    witness_artifact_sha256: str
    reproducibility_report_digest: str
    shared_input_digest: str
    byte_reproducible: bool
    owner_approval_required: bool
    automatic_publish_allowed: bool
    package_registry_write_allowed: bool
    production_integration_allowed: bool
    proof_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA,
            "state": self.state,
            "authority": self.authority,
            "module_lock_digest": self.module_lock_digest,
            "mir_version": self.mir_version,
            "mir_fingerprint": self.mir_fingerprint,
            "compiler_version": self.compiler_version,
            "backend": self.backend,
            "backend_toolchain": self.backend_toolchain,
            "release_manifest_digest": self.release_manifest_digest,
            "witness_manifest_digest": self.witness_manifest_digest,
            "release_artifact_sha256": self.release_artifact_sha256,
            "witness_artifact_sha256": self.witness_artifact_sha256,
            "reproducibility_report_digest": self.reproducibility_report_digest,
            "shared_input_digest": self.shared_input_digest,
            "byte_reproducible": self.byte_reproducible,
            "owner_approval_required": self.owner_approval_required,
            "automatic_publish_allowed": self.automatic_publish_allowed,
            "package_registry_write_allowed": self.package_registry_write_allowed,
            "production_integration_allowed": self.production_integration_allowed,
            "proof_digest": self.proof_digest,
        }


def build_release_proof(
    release: NativeBuildManifest,
    witness: NativeBuildManifest,
    report: ReproducibilityReport,
) -> ReleaseProof:
    verified_report = verify_reproducibility_report(report, release, witness)
    if verified_report.status != "byte_identical" or not verified_report.byte_reproducible:
        raise ReleaseProofError(
            "KS1930",
            "release proof requires a verified byte-identical reproducibility report",
        )
    if not verified_report.artifact_name_match:
        raise ReleaseProofError(
            "KS1930",
            "release and witness artifact names must match",
        )
    if verified_report.shared_input_digest is None:
        raise ReleaseProofError("KS1930", "shared reproducibility input digest is missing")

    payload = {
        "schema_version": _SCHEMA,
        "state": "verified_reproducible_release_candidate",
        "authority": "release_candidate_evidence_only",
        "module_lock_digest": release.module_lock_digest,
        "mir_version": release.mir_version,
        "mir_fingerprint": release.mir_fingerprint,
        "compiler_version": release.compiler_version,
        "backend": release.backend,
        "backend_toolchain": release.backend_toolchain,
        "release_manifest_digest": release.manifest_digest,
        "witness_manifest_digest": witness.manifest_digest,
        "release_artifact_sha256": release.artifact_sha256,
        "witness_artifact_sha256": witness.artifact_sha256,
        "reproducibility_report_digest": verified_report.report_digest,
        "shared_input_digest": verified_report.shared_input_digest,
        "byte_reproducible": True,
        "owner_approval_required": True,
        "automatic_publish_allowed": False,
        "package_registry_write_allowed": False,
        "production_integration_allowed": False,
    }
    return ReleaseProof(
        state=str(payload["state"]),
        authority=str(payload["authority"]),
        module_lock_digest=str(payload["module_lock_digest"]),
        mir_version=str(payload["mir_version"]),
        mir_fingerprint=str(payload["mir_fingerprint"]),
        compiler_version=str(payload["compiler_version"]),
        backend=str(payload["backend"]),
        backend_toolchain=str(payload["backend_toolchain"]),
        release_manifest_digest=str(payload["release_manifest_digest"]),
        witness_manifest_digest=str(payload["witness_manifest_digest"]),
        release_artifact_sha256=str(payload["release_artifact_sha256"]),
        witness_artifact_sha256=str(payload["witness_artifact_sha256"]),
        reproducibility_report_digest=str(payload["reproducibility_report_digest"]),
        shared_input_digest=str(payload["shared_input_digest"]),
        byte_reproducible=True,
        owner_approval_required=True,
        automatic_publish_allowed=False,
        package_registry_write_allowed=False,
        production_integration_allowed=False,
        proof_digest=_digest(payload),
    )


def load_release_proof(path: str | Path) -> ReleaseProof:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ReleaseProofError("KS1931", "release proof is not valid JSON") from error
    return _parse_proof(payload)


def verify_release_proof(
    proof: ReleaseProof,
    release: NativeBuildManifest,
    witness: NativeBuildManifest,
    report: ReproducibilityReport,
) -> ReleaseProof:
    verified = _parse_proof(proof.to_dict())
    expected = build_release_proof(release, witness, report)
    if verified.to_dict() != expected.to_dict():
        raise ReleaseProofError(
            "KS1932",
            "release proof does not match the supplied verified builds and report",
        )
    return verified


def write_release_proof(proof: ReleaseProof, destination: str | Path) -> None:
    path = Path(destination)
    if path.exists():
        raise ReleaseProofError("KS1933", f"release proof already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(proof.to_dict(), indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
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


def _parse_proof(payload: Any) -> ReleaseProof:
    if not isinstance(payload, dict):
        raise ReleaseProofError("KS1931", "release proof must be a JSON object")
    if set(payload) != _FIELDS:
        raise ReleaseProofError("KS1931", "release proof contains unsupported fields")
    if payload["schema_version"] != _SCHEMA:
        raise ReleaseProofError("KS1931", "unsupported release proof schema")
    if payload["state"] != "verified_reproducible_release_candidate":
        raise ReleaseProofError("KS1931", "invalid release proof state")
    if payload["authority"] != "release_candidate_evidence_only":
        raise ReleaseProofError("KS1931", "invalid release proof authority")

    text_fields = (
        "mir_version",
        "compiler_version",
        "backend",
        "backend_toolchain",
    )
    for field in text_fields:
        if not isinstance(payload[field], str) or not payload[field].strip():
            raise ReleaseProofError("KS1931", f"{field} must be non-empty text")

    digest_fields = (
        "module_lock_digest",
        "mir_fingerprint",
        "release_manifest_digest",
        "witness_manifest_digest",
        "release_artifact_sha256",
        "witness_artifact_sha256",
        "reproducibility_report_digest",
        "shared_input_digest",
        "proof_digest",
    )
    for field in digest_fields:
        if not _is_digest(payload[field]):
            raise ReleaseProofError("KS1931", f"{field} must be SHA-256")

    if payload["release_artifact_sha256"] != payload["witness_artifact_sha256"]:
        raise ReleaseProofError("KS1931", "release and witness artifact digests differ")
    if payload["byte_reproducible"] is not True:
        raise ReleaseProofError("KS1931", "release proof must be byte reproducible")
    if payload["owner_approval_required"] is not True:
        raise ReleaseProofError("KS1931", "release proof must require owner approval")
    for field in (
        "automatic_publish_allowed",
        "package_registry_write_allowed",
        "production_integration_allowed",
    ):
        if payload[field] is not False:
            raise ReleaseProofError("KS1931", f"{field} must remain false")

    unsigned = dict(payload)
    proof_digest = unsigned.pop("proof_digest")
    if proof_digest != _digest(unsigned):
        raise ReleaseProofError("KS1931", "release proof digest does not match contents")

    return ReleaseProof(
        state=payload["state"],
        authority=payload["authority"],
        module_lock_digest=payload["module_lock_digest"],
        mir_version=payload["mir_version"],
        mir_fingerprint=payload["mir_fingerprint"],
        compiler_version=payload["compiler_version"],
        backend=payload["backend"],
        backend_toolchain=payload["backend_toolchain"],
        release_manifest_digest=payload["release_manifest_digest"],
        witness_manifest_digest=payload["witness_manifest_digest"],
        release_artifact_sha256=payload["release_artifact_sha256"],
        witness_artifact_sha256=payload["witness_artifact_sha256"],
        reproducibility_report_digest=payload["reproducibility_report_digest"],
        shared_input_digest=payload["shared_input_digest"],
        byte_reproducible=True,
        owner_approval_required=True,
        automatic_publish_allowed=False,
        package_registry_write_allowed=False,
        production_integration_allowed=False,
        proof_digest=proof_digest,
    )


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
