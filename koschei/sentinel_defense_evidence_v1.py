"""Bind completed Sentinel defense actions to the Koschei Reality Evidence Ledger.

This layer is descriptive, not authorizing. A defense request must already be
canonical and already have been passed to the host-owned enforcer. The returned
ledger only records the observed outcome and can never be used to mint or widen
Sentinel authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Callable, Literal

from .reality_evidence_ledger_v1 import (
    RealityEvidenceLedgerV1,
    append_reality_evidence_v1,
)
from .sentinel_defense_authority_v1 import (
    SentinelDefenseAuthorityError,
    SentinelDefenseRequestV1,
    execute_sentinel_defense_request_v1,
)

_CONTEXT = b"koschei.sentinel-defense-evidence/v1\x00"


class SentinelDefenseEvidenceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SentinelDefenseEvidenceResultV1:
    enforced: bool
    outcome: Literal["ALLOW", "DENY", "FAIL"]
    ledger: RealityEvidenceLedgerV1

    def __repr__(self) -> str:
        return (
            "SentinelDefenseEvidenceResultV1("
            f"enforced={self.enforced}, outcome={self.outcome!r}, "
            "evidence_head=<committed>)"
        )


def _digest(label: bytes, value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) != 32:
        raise SentinelDefenseEvidenceError("canonical 32-byte defense digest required")
    return hashlib.sha3_256(_CONTEXT + label + b"\x00" + value).digest()


def _evidence_command(action: str) -> str:
    if action in {"quarantine", "revoke"}:
        return action
    return "observe"


def _append(
    ledger: RealityEvidenceLedgerV1,
    *,
    request: SentinelDefenseRequestV1,
    project_id: bytes,
    outcome: Literal["ALLOW", "DENY", "FAIL"],
) -> RealityEvidenceLedgerV1:
    return append_reality_evidence_v1(
        ledger,
        project_id=project_id,
        epoch=request.epoch,
        command=_evidence_command(request.action),
        authority_scope_digest=_digest(b"authority", request.delegation_digest),
        artifact_digest=_digest(b"target", request.target_commitment),
        policy_digest=_digest(b"reason", request.reason_digest),
        outcome=outcome,
    )


def execute_sentinel_defense_with_evidence_v1(
    request: SentinelDefenseRequestV1,
    *,
    project_id: bytes,
    ledger: RealityEvidenceLedgerV1,
    enforcer: Callable[[SentinelDefenseRequestV1], bool],
) -> SentinelDefenseEvidenceResultV1:
    """Enforce one already-authorized defense request and append its outcome."""
    if not isinstance(request, SentinelDefenseRequestV1):
        raise SentinelDefenseEvidenceError("canonical defense request required")
    if not isinstance(ledger, RealityEvidenceLedgerV1):
        raise SentinelDefenseEvidenceError("canonical evidence ledger required")
    if not isinstance(project_id, bytes) or len(project_id) != 16 or not any(project_id):
        raise SentinelDefenseEvidenceError("canonical project id required")

    expected_project = hashlib.sha3_256(
        b"koschei.reality-evidence-ledger/v1\x00" + b"project\x00" + project_id
    ).digest()
    if request.project_commitment != expected_project:
        raise SentinelDefenseEvidenceError("defense request/evidence project mismatch")

    try:
        enforced = execute_sentinel_defense_request_v1(request, enforcer=enforcer)
    except SentinelDefenseAuthorityError:
        updated = _append(ledger, request=request, project_id=project_id, outcome="FAIL")
        return SentinelDefenseEvidenceResultV1(
            enforced=False,
            outcome="FAIL",
            ledger=updated,
        )

    outcome: Literal["ALLOW", "DENY"] = "ALLOW" if enforced else "DENY"
    updated = _append(ledger, request=request, project_id=project_id, outcome=outcome)
    return SentinelDefenseEvidenceResultV1(
        enforced=enforced,
        outcome=outcome,
        ledger=updated,
    )
