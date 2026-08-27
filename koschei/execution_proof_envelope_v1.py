"""Machine-verifiable provenance envelope for the Koschei execution trust chain v1.

The envelope is not a new authority object and carries no secret-derived authority.
It aggregates exact digests only after re-verifying the existing chain:

external grant -> admitted evidence -> native MIR/request/proof/bound proof ->
canonical authority basis -> authenticated authorization decision -> authenticated
execution permit -> authenticated single-use consumption receipt.

The envelope's SHA-256 seal is deterministic, not an independent signature. Its
meaning comes from re-validation of the authenticated/sealed objects supplied to
`assert_valid`. V1 proves accepted permit consumption; it deliberately does not
claim that the requested external side effect completed after consumption.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .authorization_decision_v1 import AuthorizationDecisionV1
from .canonical_authority_basis_v1 import CanonicalAuthorityBasisV1
from .execution_permit_v1 import ExecutionConsumptionReceiptV1, ExecutionPermitV1
from .external_adapter_contract_v1 import ExternalAdapterEvidenceV1, ExternalAdapterGrantV1
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_proof_pipeline_v1 import NativeSigilProofBundle
from .native_sigil_request_binding_v1 import CanonicalEffectRequest, RequestBoundProof

_CTX = b"koschei.execution-proof-envelope/v1\x00"


class ExecutionProofEnvelopeV1Error(ValueError):
    pass


def _envelope_digest(*, grant: ExternalAdapterGrantV1,
                     evidence: ExternalAdapterEvidenceV1,
                     mir: NativeSigilMir,
                     request: CanonicalEffectRequest,
                     proof: NativeSigilProofBundle,
                     bound: RequestBoundProof,
                     basis: CanonicalAuthorityBasisV1,
                     decision: AuthorizationDecisionV1,
                     permit: ExecutionPermitV1,
                     consumption: ExecutionConsumptionReceiptV1) -> str:
    rows = (
        f"grant={grant.grant_digest}",
        f"evidence={evidence.evidence_digest}",
        f"mir={mir.fingerprint}",
        f"universe={mir.universe_plan_digest}",
        f"request={request.digest}",
        f"native_proof={proof.digest}",
        f"request_bound_proof={bound.digest}",
        f"authority_basis={basis.basis_digest}",
        f"authorization_decision={decision.decision_digest}",
        f"permit={permit.permit_digest}",
        f"consumption={consumption.receipt_digest}",
        f"subject_scope={basis.subject_scope_digest}",
        f"operation={basis.operation}",
        f"epoch={basis.epoch}",
        "terminal=permit-consumed",
        "authority=0",
    )
    return hashlib.sha256(_CTX + "\n".join(rows).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ExecutionProofEnvelopeV1:
    grant_digest: str
    evidence_digest: str
    native_mir_fingerprint: str
    universe_plan_digest: str
    canonical_request_digest: str
    native_proof_digest: str
    request_bound_proof_digest: str
    authority_basis_digest: str
    authorization_decision_digest: str
    permit_digest: str
    consumption_receipt_digest: str
    subject_scope_digest: str
    operation: str
    epoch: int
    terminal_state: str
    envelope_digest: str
    authority: bool = False
    version: int = 1

    def assert_valid(self, *,
                     grant: ExternalAdapterGrantV1,
                     evidence: ExternalAdapterEvidenceV1,
                     mir: NativeSigilMir,
                     request: CanonicalEffectRequest,
                     proof: NativeSigilProofBundle,
                     bound: RequestBoundProof,
                     basis: CanonicalAuthorityBasisV1,
                     decision: AuthorizationDecisionV1,
                     permit: ExecutionPermitV1,
                     consumption: ExecutionConsumptionReceiptV1,
                     decision_key: bytes,
                     runtime_key: bytes) -> None:
        if self.authority:
            raise ExecutionProofEnvelopeV1Error("proof envelope cannot carry ambient authority")
        if self.terminal_state != "permit-consumed":
            raise ExecutionProofEnvelopeV1Error("unknown proof-envelope terminal state")

        grant.assert_sealed()
        evidence.assert_sealed(grant)
        mir.assert_sealed()
        request.assert_sealed(mir)
        bound.assert_sealed(mir, request, proof)
        basis.assert_sealed(mir=mir, request=request, proof=proof, bound=bound)
        decision.assert_authenticated(decision_key=decision_key, grant=grant, evidence=evidence)
        decision.assert_allows()
        permit.assert_authenticated(runtime_key=runtime_key, decision_key=decision_key,
                                    grant=grant, evidence=evidence, decision=decision)
        consumption.assert_authenticated(runtime_key=runtime_key, permit=permit)

        if decision.authority_basis_digest != basis.basis_digest:
            raise ExecutionProofEnvelopeV1Error("authorization decision is not bound to authority basis")
        if decision.policy_digest != mir.fingerprint:
            raise ExecutionProofEnvelopeV1Error("authorization policy identity is not native MIR")
        if decision.operation != basis.operation or permit.operation != basis.operation:
            raise ExecutionProofEnvelopeV1Error("operation provenance mismatch")
        if decision.request_digest != request.digest or permit.request_digest != request.digest:
            raise ExecutionProofEnvelopeV1Error("request provenance mismatch")
        if decision.decision_epoch != basis.epoch or permit.valid_epoch != basis.epoch:
            raise ExecutionProofEnvelopeV1Error("epoch provenance mismatch")
        if decision.subject_scope_digest != basis.subject_scope_digest:
            raise ExecutionProofEnvelopeV1Error("subject-scope provenance mismatch")

        expected_fields = (
            (self.grant_digest, grant.grant_digest, "grant"),
            (self.evidence_digest, evidence.evidence_digest, "evidence"),
            (self.native_mir_fingerprint, mir.fingerprint, "native MIR"),
            (self.universe_plan_digest, mir.universe_plan_digest, "Universe plan"),
            (self.canonical_request_digest, request.digest, "canonical request"),
            (self.native_proof_digest, proof.digest, "native proof"),
            (self.request_bound_proof_digest, bound.digest, "request-bound proof"),
            (self.authority_basis_digest, basis.basis_digest, "authority basis"),
            (self.authorization_decision_digest, decision.decision_digest, "authorization decision"),
            (self.permit_digest, permit.permit_digest, "permit"),
            (self.consumption_receipt_digest, consumption.receipt_digest, "consumption receipt"),
            (self.subject_scope_digest, basis.subject_scope_digest, "subject scope"),
            (self.operation, basis.operation, "operation"),
            (self.epoch, basis.epoch, "epoch"),
        )
        for actual, expected, label in expected_fields:
            if actual != expected:
                raise ExecutionProofEnvelopeV1Error(f"proof-envelope {label} mismatch")

        expected_digest = _envelope_digest(
            grant=grant, evidence=evidence, mir=mir, request=request, proof=proof,
            bound=bound, basis=basis, decision=decision, permit=permit,
            consumption=consumption,
        )
        if self.envelope_digest != expected_digest:
            raise ExecutionProofEnvelopeV1Error("execution proof-envelope seal mismatch")


def seal_execution_proof_envelope_v1(*,
                                     grant: ExternalAdapterGrantV1,
                                     evidence: ExternalAdapterEvidenceV1,
                                     mir: NativeSigilMir,
                                     request: CanonicalEffectRequest,
                                     proof: NativeSigilProofBundle,
                                     bound: RequestBoundProof,
                                     basis: CanonicalAuthorityBasisV1,
                                     decision: AuthorizationDecisionV1,
                                     permit: ExecutionPermitV1,
                                     consumption: ExecutionConsumptionReceiptV1,
                                     decision_key: bytes,
                                     runtime_key: bytes) -> ExecutionProofEnvelopeV1:
    """Seal one aggregate receipt only after the complete bootstrap chain verifies."""
    basis.assert_sealed(mir=mir, request=request, proof=proof, bound=bound)
    decision.assert_authenticated(decision_key=decision_key, grant=grant, evidence=evidence)
    decision.assert_allows()
    permit.assert_authenticated(runtime_key=runtime_key, decision_key=decision_key,
                                grant=grant, evidence=evidence, decision=decision)
    consumption.assert_authenticated(runtime_key=runtime_key, permit=permit)
    if decision.authority_basis_digest != basis.basis_digest:
        raise ExecutionProofEnvelopeV1Error("authorization decision is not bound to authority basis")
    if decision.policy_digest != mir.fingerprint:
        raise ExecutionProofEnvelopeV1Error("authorization policy identity is not native MIR")
    if decision.request_digest != request.digest or permit.request_digest != request.digest:
        raise ExecutionProofEnvelopeV1Error("request provenance mismatch")
    if decision.operation != basis.operation or permit.operation != basis.operation:
        raise ExecutionProofEnvelopeV1Error("operation provenance mismatch")
    if decision.decision_epoch != basis.epoch or permit.valid_epoch != basis.epoch:
        raise ExecutionProofEnvelopeV1Error("epoch provenance mismatch")

    result = ExecutionProofEnvelopeV1(
        grant_digest=grant.grant_digest,
        evidence_digest=evidence.evidence_digest,
        native_mir_fingerprint=mir.fingerprint,
        universe_plan_digest=mir.universe_plan_digest,
        canonical_request_digest=request.digest,
        native_proof_digest=proof.digest,
        request_bound_proof_digest=bound.digest,
        authority_basis_digest=basis.basis_digest,
        authorization_decision_digest=decision.decision_digest,
        permit_digest=permit.permit_digest,
        consumption_receipt_digest=consumption.receipt_digest,
        subject_scope_digest=basis.subject_scope_digest,
        operation=basis.operation,
        epoch=basis.epoch,
        terminal_state="permit-consumed",
        envelope_digest="",
    )
    object.__setattr__(result, "envelope_digest", _envelope_digest(
        grant=grant, evidence=evidence, mir=mir, request=request, proof=proof,
        bound=bound, basis=basis, decision=decision, permit=permit,
        consumption=consumption,
    ))
    result.assert_valid(
        grant=grant, evidence=evidence, mir=mir, request=request, proof=proof,
        bound=bound, basis=basis, decision=decision, permit=permit,
        consumption=consumption, decision_key=decision_key, runtime_key=runtime_key,
    )
    return result
