"""Koschei Vormir Sacrifice Law v1.

Vormir is a root-reality admission primitive, not secrecy-by-obscurity.
High-value authority requires cryptographically committed attenuation of an
existing authority. No personal device identifiers are collected here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

_CTX = b"koschei.vormir-sacrifice/v1\x00"


class VormirSacrificeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SacrificeCommitmentV1:
    principal_digest: bytes
    artifact_digest: bytes
    surrendered_authority: str
    requested_authority: str
    prior_epoch: int
    next_epoch: int
    hardware_attestation_digest: bytes
    verifier_digest: bytes
    commitment_digest: bytes


def _d32(value: bytes, name: str) -> bytes:
    if not isinstance(value, bytes) or len(value) != 32:
        raise VormirSacrificeError(f"{name} must be exactly 32 bytes")
    return value


def commit_sacrifice_v1(*, principal_digest: bytes, artifact_digest: bytes,
    surrendered_authority: str, requested_authority: str, prior_epoch: int,
    next_epoch: int, hardware_attestation_digest: bytes,
    verifier_digest: bytes) -> SacrificeCommitmentV1:
    principal = _d32(principal_digest, "principal_digest")
    artifact = _d32(artifact_digest, "artifact_digest")
    attest = _d32(hardware_attestation_digest, "hardware_attestation_digest")
    verifier = _d32(verifier_digest, "verifier_digest")
    if not surrendered_authority or not requested_authority:
        raise VormirSacrificeError("authorities must be explicit")
    if surrendered_authority == requested_authority:
        raise VormirSacrificeError("sacrifice must attenuate a distinct authority")
    if prior_epoch < 0 or next_epoch != prior_epoch + 1:
        raise VormirSacrificeError("Vormir requires exactly one monotonic epoch transition")
    fields = (
        principal, artifact, surrendered_authority.encode("utf-8"),
        requested_authority.encode("utf-8"), str(prior_epoch).encode("ascii"),
        str(next_epoch).encode("ascii"), attest, verifier,
    )
    digest = hashlib.sha3_256(_CTX + b"\x00".join(fields)).digest()
    return SacrificeCommitmentV1(principal, artifact, surrendered_authority,
        requested_authority, prior_epoch, next_epoch, attest, verifier, digest)


def admits_vormir_root_v1(commitment: SacrificeCommitmentV1, *,
    revoked_authority: str, observed_epoch: int,
    observed_artifact_digest: bytes) -> bool:
    """Fail closed unless the committed authority is actually gone and reality matches."""
    if not isinstance(commitment, SacrificeCommitmentV1):
        return False
    try:
        artifact = _d32(observed_artifact_digest, "observed_artifact_digest")
    except VormirSacrificeError:
        return False
    return (
        revoked_authority == commitment.surrendered_authority
        and observed_epoch == commitment.next_epoch
        and artifact == commitment.artifact_digest
    )
