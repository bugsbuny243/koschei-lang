"""Koschei Trust Plane v1 — deterministic, fail-closed launch authorization.

This module deliberately does not execute a process, read secrets, sign payloads,
or deploy anything.  It decides whether an already-built, reproducible artifact
is eligible to receive a bounded capability set under one exact local policy.

Authority model:
- the artifact asks for capabilities;
- the artifact manifest binds to one canonical local policy hash;
- the local policy is authoritative for what may be granted;
- the release proof is provenance evidence, not deployment authority;
- artifact lifetime and deployment authorization lifetime are separate concerns.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .build_manifest import NativeBuildManifest
from .release_proof import ReleaseProof

_POLICY_SCHEMA = "koschei.trust-policy.v1"
_ARTIFACT_SCHEMA = "koschei.trust-artifact-manifest.v1"
_DECISION_SCHEMA = "koschei.trust-launch-decision.v1"

# V1 is intentionally closed-world. Adding a new authority requires a code and
# policy review; an unknown string never becomes authority by accident.
KNOWN_CAPABILITIES = frozenset(
    {
        "disk.read",
        "disk.write",
        "net.io",
        "env.read",
        "process.exec",
        "secret.use",
        "signing.request",
        "deploy.execute",
    }
)


class TrustPlaneError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class LocalPolicy:
    environment: str
    allowed_capabilities: tuple[str, ...]
    policy_hash: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": _POLICY_SCHEMA,
            "environment": self.environment,
            "allowed_capabilities": list(self.allowed_capabilities),
            "policy_hash": self.policy_hash,
        }


@dataclass(frozen=True)
class TrustArtifactManifest:
    artifact_sha256: str
    build_manifest_digest: str
    release_proof_digest: str
    policy_hash: str
    requested_capabilities: tuple[str, ...]
    manifest_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": _ARTIFACT_SCHEMA,
            "artifact_sha256": self.artifact_sha256,
            "build_manifest_digest": self.build_manifest_digest,
            "release_proof_digest": self.release_proof_digest,
            "policy_hash": self.policy_hash,
            "requested_capabilities": list(self.requested_capabilities),
            "manifest_digest": self.manifest_digest,
        }


@dataclass(frozen=True)
class LaunchDecision:
    allowed: bool
    code: str
    reason: str
    artifact_sha256: str
    policy_hash: str
    effective_capabilities: tuple[str, ...]
    decision_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": _DECISION_SCHEMA,
            "allowed": self.allowed,
            "code": self.code,
            "reason": self.reason,
            "artifact_sha256": self.artifact_sha256,
            "policy_hash": self.policy_hash,
            "effective_capabilities": list(self.effective_capabilities),
            "decision_digest": self.decision_digest,
        }


def build_local_policy(
    environment: str,
    *,
    allowed_capabilities: Iterable[str],
) -> LocalPolicy:
    env = _non_empty_text(environment, "environment")
    allowed = _canonical_capabilities(allowed_capabilities, field="allowed_capabilities")
    payload = {
        "schema_version": _POLICY_SCHEMA,
        "environment": env,
        "allowed_capabilities": list(allowed),
    }
    return LocalPolicy(
        environment=env,
        allowed_capabilities=allowed,
        policy_hash=_digest(payload),
    )


def build_trust_artifact_manifest(
    build: NativeBuildManifest,
    release_proof: ReleaseProof,
    *,
    policy_hash: str,
    requested_capabilities: Iterable[str],
) -> TrustArtifactManifest:
    _validate_build_manifest_identity(build)
    _validate_release_proof_identity(release_proof)
    _validate_release_link(build, release_proof)
    policy = _digest_field(policy_hash, "policy_hash")
    requested = _canonical_capabilities(
        requested_capabilities,
        field="requested_capabilities",
    )
    payload = {
        "schema_version": _ARTIFACT_SCHEMA,
        "artifact_sha256": build.artifact_sha256,
        "build_manifest_digest": build.manifest_digest,
        "release_proof_digest": release_proof.proof_digest,
        "policy_hash": policy,
        "requested_capabilities": list(requested),
    }
    return TrustArtifactManifest(
        artifact_sha256=build.artifact_sha256,
        build_manifest_digest=build.manifest_digest,
        release_proof_digest=release_proof.proof_digest,
        policy_hash=policy,
        requested_capabilities=requested,
        manifest_digest=_digest(payload),
    )


def evaluate_launch(
    artifact_manifest: TrustArtifactManifest,
    *,
    local_policy: LocalPolicy,
    build: NativeBuildManifest,
    release_proof: ReleaseProof,
    artifact: str | Path | None = None,
) -> LaunchDecision:
    """Return one deterministic launch decision; never grants ambient authority."""

    try:
        _validate_policy(local_policy)
        _validate_artifact_manifest(artifact_manifest)
        _validate_build_manifest_identity(build)
        _validate_release_proof_identity(release_proof)
        _validate_release_link(build, release_proof)
    except TrustPlaneError as error:
        return _deny(artifact_manifest, local_policy, error.code, error.message)

    if artifact_manifest.build_manifest_digest != build.manifest_digest:
        return _deny(
            artifact_manifest,
            local_policy,
            "KS1952",
            "artifact manifest is bound to a different build manifest",
        )
    if artifact_manifest.release_proof_digest != release_proof.proof_digest:
        return _deny(
            artifact_manifest,
            local_policy,
            "KS1953",
            "artifact manifest is bound to a different release proof",
        )
    if artifact_manifest.artifact_sha256 != build.artifact_sha256:
        return _deny(
            artifact_manifest,
            local_policy,
            "KS1954",
            "artifact identity does not match the verified build",
        )
    if artifact_manifest.policy_hash != local_policy.policy_hash:
        return _deny(
            artifact_manifest,
            local_policy,
            "KS1955",
            "artifact policy hash does not match the authoritative local policy",
        )

    requested = set(artifact_manifest.requested_capabilities)
    allowed = set(local_policy.allowed_capabilities)
    excess = tuple(sorted(requested - allowed))
    if excess:
        return _deny(
            artifact_manifest,
            local_policy,
            "KS1956",
            "requested capability is not granted by local policy: " + ", ".join(excess),
        )

    if artifact is not None:
        path = Path(artifact)
        if not path.is_file():
            return _deny(
                artifact_manifest,
                local_policy,
                "KS1957",
                "launch artifact is missing",
            )
        actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_digest != artifact_manifest.artifact_sha256:
            return _deny(
                artifact_manifest,
                local_policy,
                "KS1957",
                "launch artifact bytes do not match the authorized artifact identity",
            )

    return _decision(
        allowed=True,
        code="KS1950",
        reason="exact artifact, release proof, policy, and requested capabilities verified",
        artifact_sha256=artifact_manifest.artifact_sha256,
        policy_hash=local_policy.policy_hash,
        effective_capabilities=artifact_manifest.requested_capabilities,
    )


def _validate_policy(policy: LocalPolicy) -> None:
    environment = _non_empty_text(policy.environment, "environment")
    capabilities = _canonical_capabilities(
        policy.allowed_capabilities,
        field="allowed_capabilities",
    )
    if capabilities != policy.allowed_capabilities:
        raise TrustPlaneError("KS1951", "local policy capabilities are not canonical")
    expected = _digest(
        {
            "schema_version": _POLICY_SCHEMA,
            "environment": environment,
            "allowed_capabilities": list(capabilities),
        }
    )
    if policy.policy_hash != expected:
        raise TrustPlaneError("KS1951", "local policy hash does not match policy contents")


def _validate_artifact_manifest(manifest: TrustArtifactManifest) -> None:
    artifact = _digest_field(manifest.artifact_sha256, "artifact_sha256")
    build_digest = _digest_field(manifest.build_manifest_digest, "build_manifest_digest")
    proof_digest = _digest_field(manifest.release_proof_digest, "release_proof_digest")
    policy_hash = _digest_field(manifest.policy_hash, "policy_hash")
    capabilities = _canonical_capabilities(
        manifest.requested_capabilities,
        field="requested_capabilities",
    )
    if capabilities != manifest.requested_capabilities:
        raise TrustPlaneError("KS1951", "requested capabilities are not canonical")
    expected = _digest(
        {
            "schema_version": _ARTIFACT_SCHEMA,
            "artifact_sha256": artifact,
            "build_manifest_digest": build_digest,
            "release_proof_digest": proof_digest,
            "policy_hash": policy_hash,
            "requested_capabilities": list(capabilities),
        }
    )
    if manifest.manifest_digest != expected:
        raise TrustPlaneError("KS1951", "trust artifact manifest digest does not match contents")


def _validate_build_manifest_identity(build: NativeBuildManifest) -> None:
    payload = build.to_dict()
    digest = payload.get("manifest_digest")
    if not isinstance(digest, str) or not _is_digest(digest):
        raise TrustPlaneError("KS1951", "build manifest digest is invalid")
    unsigned = dict(payload)
    unsigned.pop("manifest_digest", None)
    if digest != _digest(unsigned):
        raise TrustPlaneError("KS1951", "build manifest digest does not match contents")
    _digest_field(build.artifact_sha256, "artifact_sha256")


def _validate_release_proof_identity(proof: ReleaseProof) -> None:
    payload = proof.to_dict()
    digest = payload.get("proof_digest")
    if not isinstance(digest, str) or not _is_digest(digest):
        raise TrustPlaneError("KS1951", "release proof digest is invalid")
    unsigned = dict(payload)
    unsigned.pop("proof_digest", None)
    if digest != _digest(unsigned):
        raise TrustPlaneError("KS1951", "release proof digest does not match contents")
    if proof.byte_reproducible is not True:
        raise TrustPlaneError("KS1951", "release proof is not byte reproducible")


def _validate_release_link(build: NativeBuildManifest, proof: ReleaseProof) -> None:
    if proof.release_manifest_digest != build.manifest_digest:
        raise TrustPlaneError("KS1951", "release proof does not bind the supplied build manifest")
    if proof.release_artifact_sha256 != build.artifact_sha256:
        raise TrustPlaneError("KS1951", "release proof does not bind the supplied artifact")


def _canonical_capabilities(values: Iterable[str], *, field: str) -> tuple[str, ...]:
    normalized: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise TrustPlaneError("KS1951", f"{field} contains an invalid capability")
        capability = value.strip()
        if capability not in KNOWN_CAPABILITIES:
            raise TrustPlaneError("KS1951", f"unknown capability: {capability}")
        normalized.add(capability)
    return tuple(sorted(normalized))


def _deny(
    manifest: TrustArtifactManifest,
    policy: LocalPolicy,
    code: str,
    reason: str,
) -> LaunchDecision:
    artifact_sha256 = manifest.artifact_sha256 if _is_digest(manifest.artifact_sha256) else "0" * 64
    policy_hash = policy.policy_hash if _is_digest(policy.policy_hash) else "0" * 64
    return _decision(
        allowed=False,
        code=code,
        reason=reason,
        artifact_sha256=artifact_sha256,
        policy_hash=policy_hash,
        effective_capabilities=(),
    )


def _decision(
    *,
    allowed: bool,
    code: str,
    reason: str,
    artifact_sha256: str,
    policy_hash: str,
    effective_capabilities: tuple[str, ...],
) -> LaunchDecision:
    payload = {
        "schema_version": _DECISION_SCHEMA,
        "allowed": allowed,
        "code": code,
        "reason": reason,
        "artifact_sha256": artifact_sha256,
        "policy_hash": policy_hash,
        "effective_capabilities": list(effective_capabilities),
    }
    return LaunchDecision(
        allowed=allowed,
        code=code,
        reason=reason,
        artifact_sha256=artifact_sha256,
        policy_hash=policy_hash,
        effective_capabilities=effective_capabilities,
        decision_digest=_digest(payload),
    )


def _non_empty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrustPlaneError("KS1951", f"{field} must be non-empty text")
    return value.strip()


def _digest_field(value: object, field: str) -> str:
    if not isinstance(value, str) or not _is_digest(value):
        raise TrustPlaneError("KS1951", f"{field} must be a SHA-256 digest")
    return value


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
