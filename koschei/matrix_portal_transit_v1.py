"""Matrix Portal Transit v1.

Cross-Reality movement is explicit, commitment-bound and non-authoritative by itself.
A portal proof binds source and destination Reality commitments, payload identity,
requested effect, exact target and epoch. Connectivity never implies authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .wanda_reality_integrity_v1 import RealityCommitmentV1

_CTX = b"koschei.matrix-portal-transit/v1\x00"


class MatrixPortalTransitError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PortalTransitProofV1:
    source_reality: str
    destination_reality: str
    source_commitment: bytes
    destination_commitment: bytes
    payload_digest: bytes
    effect: str
    target_digest: bytes
    epoch: int
    transit_digest: bytes


def _d32(value: bytes, label: str) -> bytes:
    if not isinstance(value, bytes) or len(value) != 32:
        raise MatrixPortalTransitError(f"{label} must be exactly 32 bytes")
    return value


def create_portal_transit_proof_v1(*, source: RealityCommitmentV1,
    destination: RealityCommitmentV1, payload_digest: bytes, effect: str,
    target_digest: bytes, epoch: int) -> PortalTransitProofV1:
    if not isinstance(source, RealityCommitmentV1) or not isinstance(destination, RealityCommitmentV1):
        raise MatrixPortalTransitError("canonical source and destination Reality commitments required")
    if source.reality_id == destination.reality_id:
        raise MatrixPortalTransitError("portal transit requires distinct Realities")
    payload = _d32(payload_digest, "payload_digest")
    target = _d32(target_digest, "target_digest")
    if not effect:
        raise MatrixPortalTransitError("effect must be explicit")
    if not isinstance(epoch, int) or epoch < 0:
        raise MatrixPortalTransitError("invalid portal epoch")
    body = b"\x00".join((
        source.reality_id.encode(), destination.reality_id.encode(),
        source.commitment_digest, destination.commitment_digest,
        payload, effect.encode(), target, str(epoch).encode(),
    ))
    digest = hashlib.sha3_256(_CTX + body).digest()
    return PortalTransitProofV1(source.reality_id, destination.reality_id,
        source.commitment_digest, destination.commitment_digest, payload,
        effect, target, epoch, digest)


def portal_matches_reality_v1(proof: PortalTransitProofV1, *,
    source: RealityCommitmentV1, destination: RealityCommitmentV1,
    payload_digest: bytes, effect: str, target_digest: bytes, epoch: int) -> bool:
    if not isinstance(proof, PortalTransitProofV1):
        return False
    try:
        payload = _d32(payload_digest, "payload_digest")
        target = _d32(target_digest, "target_digest")
    except MatrixPortalTransitError:
        return False
    return (
        proof.source_reality == source.reality_id
        and proof.destination_reality == destination.reality_id
        and proof.source_commitment == source.commitment_digest
        and proof.destination_commitment == destination.commitment_digest
        and proof.payload_digest == payload
        and proof.effect == effect
        and proof.target_digest == target
        and proof.epoch == epoch
    )
