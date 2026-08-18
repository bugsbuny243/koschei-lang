"""Koschei Library Quarantine Contract v1.

Turns formal composite library risk evidence into a fail-safe admission barrier.
The contract does not let evidence or Sentinel mint authority. Instead, compound
risk causes the current library execution lease to become non-renewable until a
fresh, independently issued proof/admission is supplied.

Core law: evidence can remove continuation, never create power.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .library_risk_evidence_v1 import CompositeLibraryRiskEvidenceV1

_CONTEXT = b"koschei.library-quarantine-contract/v1\x00"


class LibraryQuarantineContractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LibraryExecutionLeaseV1:
    artifact_digest: bytes
    revision_digest: bytes
    epoch: int
    not_before: int
    expires_at: int
    lease_digest: bytes


@dataclass(frozen=True, slots=True)
class LibraryQuarantineDecisionV1:
    quarantined: bool
    artifact_digest: bytes
    evidence_digest: bytes
    lease_digest: bytes
    reason: str
    decision_digest: bytes


@dataclass(frozen=True, slots=True)
class LibraryRecoveryProofV1:
    artifact_digest: bytes
    prior_evidence_digest: bytes
    repaired_revision_digest: bytes
    new_epoch: int
    verifier_digest: bytes
    proof_digest: bytes


def _fail(message: str) -> None:
    raise LibraryQuarantineContractError(message)


def _d32(value: bytes, label: str) -> bytes:
    if not isinstance(value, bytes) or len(value) != 32:
        _fail(f"{label} must be exactly 32 bytes")
    return value


def issue_library_execution_lease_v1(*, artifact_digest: bytes, revision_digest: bytes,
    epoch: int, not_before: int, expires_at: int, host_nonce: bytes) -> LibraryExecutionLeaseV1:
    artifact = _d32(artifact_digest, "artifact digest")
    revision = _d32(revision_digest, "revision digest")
    nonce = _d32(host_nonce, "host nonce")
    if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 1:
        _fail("epoch must be positive")
    if not isinstance(not_before, int) or not isinstance(expires_at, int) or expires_at <= not_before:
        _fail("invalid execution lease window")
    if expires_at - not_before > 120:
        _fail("execution lease exceeds 120 seconds")
    payload = b"\x00".join((artifact, revision, epoch.to_bytes(8,"big"),
        not_before.to_bytes(8,"big"), expires_at.to_bytes(8,"big"), nonce))
    digest = hashlib.sha3_256(_CONTEXT + b"lease\x00" + payload).digest()
    return LibraryExecutionLeaseV1(artifact, revision, epoch, not_before, expires_at, digest)


def evaluate_library_quarantine_v1(*, lease: LibraryExecutionLeaseV1,
    evidence: CompositeLibraryRiskEvidenceV1, now: int) -> LibraryQuarantineDecisionV1:
    if not isinstance(lease, LibraryExecutionLeaseV1):
        _fail("canonical execution lease required")
    if not isinstance(evidence, CompositeLibraryRiskEvidenceV1):
        _fail("canonical risk evidence required")
    if evidence.artifact_digest != lease.artifact_digest:
        _fail("evidence/lease artifact mismatch")
    if not isinstance(now, int) or now < lease.not_before or now >= lease.expires_at:
        quarantined = True
        reason = "lease-inactive"
    elif evidence.compound:
        quarantined = True
        reason = "compound-risk-evidence"
    else:
        quarantined = False
        reason = "single-dimension-evidence"
    payload = b"\x00".join((lease.artifact_digest, evidence.evidence_digest,
        lease.lease_digest, reason.encode("ascii"), b"1" if quarantined else b"0"))
    digest = hashlib.sha3_256(_CONTEXT + b"decision\x00" + payload).digest()
    return LibraryQuarantineDecisionV1(quarantined, lease.artifact_digest,
        evidence.evidence_digest, lease.lease_digest, reason, digest)


def issue_library_recovery_proof_v1(*, quarantined: LibraryQuarantineDecisionV1,
    repaired_revision_digest: bytes, new_epoch: int, verifier_digest: bytes) -> LibraryRecoveryProofV1:
    if not isinstance(quarantined, LibraryQuarantineDecisionV1) or not quarantined.quarantined:
        _fail("recovery proof requires a canonical quarantine decision")
    revision = _d32(repaired_revision_digest, "repaired revision digest")
    verifier = _d32(verifier_digest, "verifier digest")
    if not isinstance(new_epoch, int) or isinstance(new_epoch, bool) or new_epoch < 1:
        _fail("new epoch must be positive")
    payload = b"\x00".join((quarantined.artifact_digest, quarantined.evidence_digest,
        revision, new_epoch.to_bytes(8,"big"), verifier))
    proof = hashlib.sha3_256(_CONTEXT + b"recovery\x00" + payload).digest()
    return LibraryRecoveryProofV1(quarantined.artifact_digest,
        quarantined.evidence_digest, revision, new_epoch, verifier, proof)


def recovery_proof_allows_fresh_lease_v1(proof: LibraryRecoveryProofV1, *,
    prior_lease: LibraryExecutionLeaseV1) -> bool:
    if not isinstance(proof, LibraryRecoveryProofV1) or not isinstance(prior_lease, LibraryExecutionLeaseV1):
        _fail("canonical recovery proof and prior lease required")
    if proof.artifact_digest != prior_lease.artifact_digest:
        return False
    if proof.repaired_revision_digest == prior_lease.revision_digest:
        return False
    if proof.new_epoch <= prior_lease.epoch:
        return False
    return True
