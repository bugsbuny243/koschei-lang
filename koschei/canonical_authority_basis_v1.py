"""Canonical authority-basis receipts from Koschei's native enforcement chain v1.

This module does not create a second capability system.  It turns the existing
native privileged-effect path -- sealed MIR, canonical request, request-bound
proof, and enforcement decision -- into one deterministic receipt that later
external-adapter authorization code can verify and reference.

The receipt carries no ambient authority.  It is evidence that the canonical
Koschei enforcement machinery reached ALLOW, DENY, or CONTAIN for one exact
request under one exact MIR/proof world.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .native_sigil_enforcement_gate_v1 import (
    EnforcementDecision,
    PrivilegedEffectIntent,
    evaluate_enforcement,
)
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_proof_pipeline_v1 import NativeSigilProofBundle
from .native_sigil_request_binding_v1 import CanonicalEffectRequest, RequestBoundProof

_CTX = b"koschei.canonical-authority-basis/v1\x00"
_SUBJECT_CTX = b"koschei.canonical-subject-scope/v1\x00"


class CanonicalAuthorityBasisV1Error(ValueError):
    pass


def canonical_subject_scope_digest_v1(request: CanonicalEffectRequest) -> str:
    """Derive external-adapter subject scope from a sealed canonical request identity."""
    if not request.subject or not request.identity_digest:
        raise CanonicalAuthorityBasisV1Error("canonical request subject identity is incomplete")
    payload = f"subject={request.subject}\nidentity={request.identity_digest}".encode("utf-8")
    return hashlib.sha256(_SUBJECT_CTX + payload).hexdigest()


def _basis_digest(
    *,
    request: CanonicalEffectRequest,
    bound: RequestBoundProof,
    decision: EnforcementDecision,
    mir: NativeSigilMir,
    proof: NativeSigilProofBundle,
    subject_scope_digest: str,
) -> str:
    rows = (
        f"request={request.digest}",
        f"bound_proof={bound.digest}",
        f"enforcement_decision={decision.digest}",
        f"mir={mir.fingerprint}",
        f"universe={mir.universe_plan_digest}",
        f"proof={proof.digest}",
        f"subject_scope={subject_scope_digest}",
        f"operation={request.operation}",
        f"epoch={request.epoch}",
        f"outcome={decision.decision}",
    )
    return hashlib.sha256(_CTX + "\n".join(rows).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CanonicalAuthorityBasisV1:
    canonical_request_digest: str
    request_bound_proof_digest: str
    enforcement_decision_digest: str
    native_mir_fingerprint: str
    universe_plan_digest: str
    proof_digest: str
    subject_scope_digest: str
    operation: str
    epoch: int
    outcome: str
    basis_digest: str
    authority: bool = False
    version: int = 1

    def assert_sealed(
        self,
        *,
        mir: NativeSigilMir,
        request: CanonicalEffectRequest,
        proof: NativeSigilProofBundle,
        bound: RequestBoundProof,
    ) -> EnforcementDecision:
        if self.authority:
            raise CanonicalAuthorityBasisV1Error("authority-basis receipt cannot carry ambient authority")
        mir.assert_sealed()
        request.assert_sealed(mir)
        bound.assert_sealed(mir, request, proof)
        intent = PrivilegedEffectIntent(
            effect_id=request.effect_id,
            subject=request.subject,
            operation=request.operation,
            request_digest=request.request_digest,
        )
        decision = evaluate_enforcement(mir, proof, intent)
        subject_scope = canonical_subject_scope_digest_v1(request)
        expected_fields = (
            (self.canonical_request_digest, request.digest, "canonical request"),
            (self.request_bound_proof_digest, bound.digest, "request-bound proof"),
            (self.enforcement_decision_digest, decision.digest, "enforcement decision"),
            (self.native_mir_fingerprint, mir.fingerprint, "native MIR"),
            (self.universe_plan_digest, mir.universe_plan_digest, "Universe plan"),
            (self.proof_digest, proof.digest, "proof"),
            (self.subject_scope_digest, subject_scope, "subject scope"),
            (self.operation, request.operation, "operation"),
            (self.epoch, request.epoch, "epoch"),
            (self.outcome, decision.decision, "outcome"),
        )
        for actual, expected, label in expected_fields:
            if actual != expected:
                raise CanonicalAuthorityBasisV1Error(f"authority-basis {label} mismatch")
        expected_digest = _basis_digest(
            request=request,
            bound=bound,
            decision=decision,
            mir=mir,
            proof=proof,
            subject_scope_digest=subject_scope,
        )
        if self.basis_digest != expected_digest:
            raise CanonicalAuthorityBasisV1Error("canonical authority-basis seal mismatch")
        return decision


def derive_canonical_authority_basis_v1(
    *,
    mir: NativeSigilMir,
    request: CanonicalEffectRequest,
    proof: NativeSigilProofBundle,
    bound: RequestBoundProof,
) -> CanonicalAuthorityBasisV1:
    """Derive, never caller-inject, the authority basis from native Koschei enforcement."""
    mir.assert_sealed()
    request.assert_sealed(mir)
    bound.assert_sealed(mir, request, proof)
    decision = evaluate_enforcement(
        mir,
        proof,
        PrivilegedEffectIntent(
            effect_id=request.effect_id,
            subject=request.subject,
            operation=request.operation,
            request_digest=request.request_digest,
        ),
    )
    subject_scope = canonical_subject_scope_digest_v1(request)
    result = CanonicalAuthorityBasisV1(
        canonical_request_digest=request.digest,
        request_bound_proof_digest=bound.digest,
        enforcement_decision_digest=decision.digest,
        native_mir_fingerprint=mir.fingerprint,
        universe_plan_digest=mir.universe_plan_digest,
        proof_digest=proof.digest,
        subject_scope_digest=subject_scope,
        operation=request.operation,
        epoch=request.epoch,
        outcome=decision.decision,
        basis_digest="",
    )
    object.__setattr__(
        result,
        "basis_digest",
        _basis_digest(
            request=request,
            bound=bound,
            decision=decision,
            mir=mir,
            proof=proof,
            subject_scope_digest=subject_scope,
        ),
    )
    result.assert_sealed(mir=mir, request=request, proof=proof, bound=bound)
    return result
