"""Koschei Reality Evidence Ledger v1.

The ledger is an additive, secret-redacted observation plane for the Koschei
reality fabric.  It does not grant execution authority and it cannot change
compiler/runtime truth.  Instead it binds already-completed canonical actions to
an append-only hash chain that an independent observer can inspect.

This module deliberately provides *tamper evidence*, not magical tamper
prevention.  Durable anchoring/signing belongs to an external trust plane.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from typing import Literal


_DIGEST_BYTES = 32
_PROJECT_ID_BYTES = 16
_MAX_RECORDS = 1_000_000
_CONTEXT = b"koschei.reality-evidence-ledger/v1\x00"
_GENESIS = hashlib.sha3_256(_CONTEXT + b"genesis").digest()


class RealityEvidenceError(ValueError):
    """Raised when evidence cannot be admitted canonically."""


@dataclass(frozen=True, slots=True)
class RealityEvidenceRecordV1:
    sequence: int
    project_commitment: bytes
    epoch: int
    command: Literal["check", "run", "build", "quarantine", "revoke", "observe"]
    authority_scope_digest: bytes
    artifact_digest: bytes
    policy_digest: bytes
    outcome: Literal["ALLOW", "DENY", "FAIL"]
    previous_digest: bytes
    record_digest: bytes

    def __repr__(self) -> str:
        return (
            "RealityEvidenceRecordV1("
            f"sequence={self.sequence}, command={self.command!r}, "
            f"epoch={self.epoch}, outcome={self.outcome!r}, "
            "project=<committed>, digests=<redacted>)"
        )


@dataclass(frozen=True, slots=True)
class RealityEvidenceLedgerV1:
    records: tuple[RealityEvidenceRecordV1, ...] = ()

    @property
    def head_digest(self) -> bytes:
        return self.records[-1].record_digest if self.records else _GENESIS


@dataclass(frozen=True, slots=True)
class ObserverEvidenceViewV1:
    """Read-only evidence projection.  It intentionally carries no capability."""

    sequence: int
    project_commitment: bytes
    epoch: int
    command: str
    outcome: str
    record_digest: bytes


def _digest(value: object, label: str) -> bytes:
    if not isinstance(value, bytes) or len(value) != _DIGEST_BYTES:
        raise RealityEvidenceError(f"{label} must be exactly {_DIGEST_BYTES} bytes")
    return value


def _epoch(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= (1 << 64) - 1:
        raise RealityEvidenceError("evidence epoch must be a positive uint64")
    return value


def project_commitment_v1(project_id: bytes) -> bytes:
    """Return a correlation-safe commitment instead of exposing raw project identity."""

    if not isinstance(project_id, bytes) or len(project_id) != _PROJECT_ID_BYTES or not any(project_id):
        raise RealityEvidenceError("project id must be exactly 16 non-zero bytes")
    return hashlib.sha3_256(_CONTEXT + b"project\x00" + project_id).digest()


def _record_digest(
    *,
    sequence: int,
    project_commitment: bytes,
    epoch: int,
    command: str,
    authority_scope_digest: bytes,
    artifact_digest: bytes,
    policy_digest: bytes,
    outcome: str,
    previous_digest: bytes,
) -> bytes:
    payload = b"\x00".join(
        (
            _CONTEXT,
            sequence.to_bytes(8, "big"),
            project_commitment,
            epoch.to_bytes(8, "big"),
            command.encode("ascii"),
            authority_scope_digest,
            artifact_digest,
            policy_digest,
            outcome.encode("ascii"),
            previous_digest,
        )
    )
    return hashlib.sha3_256(payload).digest()


def append_reality_evidence_v1(
    ledger: RealityEvidenceLedgerV1,
    *,
    project_id: bytes,
    epoch: int,
    command: Literal["check", "run", "build", "quarantine", "revoke", "observe"],
    authority_scope_digest: bytes,
    artifact_digest: bytes,
    policy_digest: bytes,
    outcome: Literal["ALLOW", "DENY", "FAIL"],
) -> RealityEvidenceLedgerV1:
    """Append one completed action as canonical evidence.

    Evidence is descriptive only.  Calling this function cannot authorize the
    action it describes and therefore cannot be used as an authority laundering
    primitive.
    """

    if not isinstance(ledger, RealityEvidenceLedgerV1):
        raise RealityEvidenceError("canonical evidence ledger is required")
    if len(ledger.records) >= _MAX_RECORDS:
        raise RealityEvidenceError("evidence ledger reached its bounded record limit")
    if command not in {"check", "run", "build", "quarantine", "revoke", "observe"}:
        raise RealityEvidenceError("unsupported evidence command")
    if outcome not in {"ALLOW", "DENY", "FAIL"}:
        raise RealityEvidenceError("unsupported evidence outcome")

    project = project_commitment_v1(project_id)
    reality_epoch = _epoch(epoch)
    authority = _digest(authority_scope_digest, "authority scope digest")
    artifact = _digest(artifact_digest, "artifact digest")
    policy = _digest(policy_digest, "policy digest")
    previous = ledger.head_digest
    sequence = len(ledger.records) + 1
    digest = _record_digest(
        sequence=sequence,
        project_commitment=project,
        epoch=reality_epoch,
        command=command,
        authority_scope_digest=authority,
        artifact_digest=artifact,
        policy_digest=policy,
        outcome=outcome,
        previous_digest=previous,
    )
    record = RealityEvidenceRecordV1(
        sequence=sequence,
        project_commitment=project,
        epoch=reality_epoch,
        command=command,
        authority_scope_digest=authority,
        artifact_digest=artifact,
        policy_digest=policy,
        outcome=outcome,
        previous_digest=previous,
        record_digest=digest,
    )
    return RealityEvidenceLedgerV1(ledger.records + (record,))


def verify_reality_evidence_ledger_v1(ledger: RealityEvidenceLedgerV1) -> None:
    """Verify sequence, previous-link and content digests for the whole chain."""

    if not isinstance(ledger, RealityEvidenceLedgerV1):
        raise RealityEvidenceError("canonical evidence ledger is required")
    if len(ledger.records) > _MAX_RECORDS:
        raise RealityEvidenceError("evidence ledger exceeds its bounded record limit")

    previous = _GENESIS
    for expected_sequence, record in enumerate(ledger.records, start=1):
        if not isinstance(record, RealityEvidenceRecordV1):
            raise RealityEvidenceError("ledger contains a non-canonical evidence record")
        if record.sequence != expected_sequence:
            raise RealityEvidenceError("evidence sequence is non-canonical")
        if not hmac.compare_digest(record.previous_digest, previous):
            raise RealityEvidenceError("evidence previous-link mismatch")
        expected = _record_digest(
            sequence=record.sequence,
            project_commitment=_digest(record.project_commitment, "project commitment"),
            epoch=_epoch(record.epoch),
            command=record.command,
            authority_scope_digest=_digest(record.authority_scope_digest, "authority scope digest"),
            artifact_digest=_digest(record.artifact_digest, "artifact digest"),
            policy_digest=_digest(record.policy_digest, "policy digest"),
            outcome=record.outcome,
            previous_digest=_digest(record.previous_digest, "previous digest"),
        )
        if not hmac.compare_digest(record.record_digest, expected):
            raise RealityEvidenceError("evidence record digest mismatch")
        previous = record.record_digest


def observer_evidence_view_v1(ledger: RealityEvidenceLedgerV1) -> tuple[ObserverEvidenceViewV1, ...]:
    """Expose only non-secret, non-authorizing facts to the observer plane."""

    verify_reality_evidence_ledger_v1(ledger)
    return tuple(
        ObserverEvidenceViewV1(
            sequence=record.sequence,
            project_commitment=record.project_commitment,
            epoch=record.epoch,
            command=record.command,
            outcome=record.outcome,
            record_digest=record.record_digest,
        )
        for record in ledger.records
    )
