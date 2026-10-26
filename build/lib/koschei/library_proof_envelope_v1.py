"""Deterministic proof envelope for Koschei Library execution v1.

The visible Koschei program expands into Library obligations.  This module binds
one completed proof receipt to every expansion step and seals the entire set into
one deterministic envelope.  It does not fabricate evidence: missing, duplicate,
mis-bound, or failed receipts make the envelope invalid.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from .library_expansion_engine_v1 import LibraryExpansionPlan

_CTX = b"koschei.library-proof-envelope/v1\x00"


class LibraryProofError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LibraryProofReceipt:
    activation_step_id: str
    obligation: str
    subsystem: str
    proof_kind: str
    evidence_digest: str
    success: bool
    digest: str


@dataclass(frozen=True, slots=True)
class LibraryProofEnvelope:
    expansion_plan_digest: str
    activation_plan_digest: str
    receipts: tuple[LibraryProofReceipt, ...]
    decision: str
    digest: str


def _receipt_digest(
    *,
    activation_step_id: str,
    obligation: str,
    subsystem: str,
    proof_kind: str,
    evidence_digest: str,
    success: bool,
) -> str:
    payload = "|".join(
        (
            activation_step_id,
            obligation,
            subsystem,
            proof_kind,
            evidence_digest,
            "1" if success else "0",
        )
    ).encode("utf-8")
    return hashlib.sha256(_CTX + b"receipt\x00" + payload).hexdigest()


def make_receipt(
    *,
    activation_step_id: str,
    obligation: str,
    subsystem: str,
    proof_kind: str,
    evidence_digest: str,
    success: bool = True,
) -> LibraryProofReceipt:
    if not evidence_digest:
        raise LibraryProofError("Library proof receipt requires evidence")
    return LibraryProofReceipt(
        activation_step_id=activation_step_id,
        obligation=obligation,
        subsystem=subsystem,
        proof_kind=proof_kind,
        evidence_digest=evidence_digest,
        success=success,
        digest=_receipt_digest(
            activation_step_id=activation_step_id,
            obligation=obligation,
            subsystem=subsystem,
            proof_kind=proof_kind,
            evidence_digest=evidence_digest,
            success=success,
        ),
    )


def _envelope_digest(
    plan: LibraryExpansionPlan,
    receipts: tuple[LibraryProofReceipt, ...],
    decision: str,
) -> str:
    parts = [
        f"expansion={plan.digest}",
        f"activation={plan.activation_plan_digest}",
        f"decision={decision}",
    ]
    parts.extend(f"receipt={item.digest}" for item in receipts)
    return hashlib.sha256(_CTX + b"envelope\x00" + "\n".join(parts).encode("utf-8")).hexdigest()


def seal_library_proof_envelope(
    plan: LibraryExpansionPlan,
    receipts: Iterable[LibraryProofReceipt],
) -> LibraryProofEnvelope:
    supplied = tuple(receipts)
    by_step: dict[str, LibraryProofReceipt] = {}
    for receipt in supplied:
        if receipt.activation_step_id in by_step:
            raise LibraryProofError(
                f"duplicate Library proof receipt: {receipt.activation_step_id}"
            )
        by_step[receipt.activation_step_id] = receipt

    ordered: list[LibraryProofReceipt] = []
    for step in plan.steps:
        receipt = by_step.get(step.activation_step_id)
        if receipt is None:
            raise LibraryProofError(
                f"missing Library proof receipt: {step.activation_step_id}"
            )
        if receipt.obligation != step.obligation:
            raise LibraryProofError("Library proof obligation mismatch")
        if receipt.subsystem != step.subsystem:
            raise LibraryProofError("Library proof subsystem mismatch")
        if receipt.proof_kind != step.proof_kind:
            raise LibraryProofError("Library proof kind mismatch")
        expected = _receipt_digest(
            activation_step_id=receipt.activation_step_id,
            obligation=receipt.obligation,
            subsystem=receipt.subsystem,
            proof_kind=receipt.proof_kind,
            evidence_digest=receipt.evidence_digest,
            success=receipt.success,
        )
        if receipt.digest != expected:
            raise LibraryProofError("Library proof receipt digest mismatch")
        ordered.append(receipt)

    extras = set(by_step) - {step.activation_step_id for step in plan.steps}
    if extras:
        raise LibraryProofError("proof envelope contains receipts outside the expansion plan")

    # A failed obligation never becomes ALLOW merely because every other step
    # produced evidence.  Later policy layers may map failure to DENY/CONTAIN,
    # but the Library envelope itself remains conservative.
    decision = "ALLOW" if all(item.success for item in ordered) else "DENY"
    frozen = tuple(ordered)
    return LibraryProofEnvelope(
        expansion_plan_digest=plan.digest,
        activation_plan_digest=plan.activation_plan_digest,
        receipts=frozen,
        decision=decision,
        digest=_envelope_digest(plan, frozen, decision),
    )


def require_library_proof_envelope(
    plan: LibraryExpansionPlan,
    envelope: LibraryProofEnvelope,
) -> None:
    if envelope.expansion_plan_digest != plan.digest:
        raise LibraryProofError("proof envelope expansion-plan mismatch")
    if envelope.activation_plan_digest != plan.activation_plan_digest:
        raise LibraryProofError("proof envelope activation-plan mismatch")
    resealed = seal_library_proof_envelope(plan, envelope.receipts)
    if resealed.decision != envelope.decision:
        raise LibraryProofError("proof envelope decision mismatch")
    if resealed.digest != envelope.digest:
        raise LibraryProofError("proof envelope digest mismatch")
