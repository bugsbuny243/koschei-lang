"""Matrix Portal Transit v1.

Cross-Reality movement is explicit, commitment-bound and non-authoritative by itself.
A portal proof binds source and destination Reality commitments, payload identity,
requested effect, exact target and epoch. Connectivity never implies authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .wanda_reality_integrity_v1 import RealityCommitmentV1, commit_reality_v1

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


def _canonical_reality(record: RealityCommitmentV1) -> bool:
    """A record digest is not an issuer signature, but must match its fields.

    A raw dataclass with a copied old commitment_digest must never satisfy
    a new portal proof. Independent authenticity and current-state checks
    still belong to the caller and durable execution gate.
    """
    if not isinstance(record, RealityCommitmentV1):
        return False
    try:
        expected = commit_reality_v1(
            reality_id=record.reality_id,
            epoch=record.epoch,
            state_digest=record.state_digest,
            authority_digest=record.authority_digest,
            previous_commitment=record.previous_commitment,
        )
    except (ValueError, TypeError, AttributeError):
        return False
    return record == expected


def create_portal_transit_proof_v1(*, source: RealityCommitmentV1,
    destination: RealityCommitmentV1, payload_digest: bytes, effect: str,
    target_digest: bytes, epoch: int) -> PortalTransitProofV1:
    if not _canonical_reality(source) or not _canonical_reality(destination):
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
    """Compare an independently re-derived proof, including its own digest.

    This is NOT an authorization or a durable replay fence. A caller can
    construct a new internally consistent proof for different inputs;
    authentic current-state and effect grants remain separate requirements.
    """
    if not isinstance(proof, PortalTransitProofV1):
        return False
    try:
        expected = create_portal_transit_proof_v1(
            source=source, destination=destination,
            payload_digest=payload_digest, effect=effect,
            target_digest=target_digest, epoch=epoch,
        )
    except (MatrixPortalTransitError, ValueError, TypeError, AttributeError):
        return False
    return proof == expected
