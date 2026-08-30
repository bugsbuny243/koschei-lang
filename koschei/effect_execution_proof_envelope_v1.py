"""Effect-terminal provenance envelope layered over ExecutionProofEnvelopeV1.

The base execution envelope remains a proof of `permit-consumed`. This higher layer
adds one authenticated EffectExecutionReceiptV1 and may therefore report the local
runtime terminal state `effect-completed` or `effect-failed`. It still does not prove
remote settlement/finality outside the measured callback boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .authorization_decision_v1 import AuthorizationDecisionV1
from .canonical_authority_basis_v1 import CanonicalAuthorityBasisV1
from .effect_execution_receipt_v1 import EffectExecutionReceiptV1
from .execution_permit_v1 import ExecutionConsumptionReceiptV1, ExecutionPermitV1
from .execution_proof_envelope_v1 import ExecutionProofEnvelopeV1
from .external_adapter_contract_v1 import ExternalAdapterEvidenceV1, ExternalAdapterGrantV1
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_proof_pipeline_v1 import NativeSigilProofBundle
from .native_sigil_request_binding_v1 import CanonicalEffectRequest, RequestBoundProof

_CTX = b"koschei.effect-execution-proof-envelope/v1\x00"
_TERMINALS = frozenset({"effect-completed", "effect-failed"})


class EffectExecutionProofEnvelopeV1Error(ValueError):
    pass


def _digest(base: ExecutionProofEnvelopeV1, effect: EffectExecutionReceiptV1) -> str:
    rows = (
        f"base_execution_envelope={base.envelope_digest}",
        f"effect_receipt={effect.receipt_digest}",
        f"canonical_request={effect.canonical_request_digest}",
        f"operation={effect.operation}",
        f"epoch={effect.execution_epoch}",
        f"terminal={effect.outcome}",
        f"measurement={effect.measurement_digest}",
        "authority=0",
    )
    return hashlib.sha256(_CTX + "\n".join(rows).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class EffectExecutionProofEnvelopeV1:
    base_execution_envelope_digest: str
    effect_receipt_digest: str
    canonical_request_digest: str
    operation: str
    epoch: int
    terminal_state: str
    measurement_digest: str
    envelope_digest: str
    authority: bool = False
    version: int = 1

    def assert_valid(self, *,
                     base: ExecutionProofEnvelopeV1,
                     effect_receipt: EffectExecutionReceiptV1,
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
                     runtime_key: bytes,
                     effect_key: bytes) -> None:
        if self.authority:
            raise EffectExecutionProofEnvelopeV1Error("effect proof envelope cannot carry ambient authority")
        if self.terminal_state not in _TERMINALS:
            raise EffectExecutionProofEnvelopeV1Error("unknown effect proof-envelope terminal state")
        base.assert_valid(
            grant=grant, evidence=evidence, mir=mir, request=request, proof=proof,
            bound=bound, basis=basis, decision=decision, permit=permit,
            consumption=consumption, decision_key=decision_key, runtime_key=runtime_key,
        )
        if base.terminal_state != "permit-consumed":
            raise EffectExecutionProofEnvelopeV1Error("base envelope is not permit-consumed")
        effect_receipt.assert_authenticated(
            effect_key=effect_key, consumption=consumption, permit=permit,
            mir=mir, request=request,
        )
        expected_fields = (
            (self.base_execution_envelope_digest, base.envelope_digest, "base envelope"),
            (self.effect_receipt_digest, effect_receipt.receipt_digest, "effect receipt"),
            (self.canonical_request_digest, request.digest, "canonical request"),
            (self.operation, request.operation, "operation"),
            (self.epoch, request.epoch, "epoch"),
            (self.terminal_state, effect_receipt.outcome, "terminal state"),
            (self.measurement_digest, effect_receipt.measurement_digest, "measurement"),
        )
        for actual, expected, label in expected_fields:
            if actual != expected:
                raise EffectExecutionProofEnvelopeV1Error(f"effect proof-envelope {label} mismatch")
        if self.envelope_digest != _digest(base, effect_receipt):
            raise EffectExecutionProofEnvelopeV1Error("effect execution proof-envelope seal mismatch")


def seal_effect_execution_proof_envelope_v1(*,
                                            base: ExecutionProofEnvelopeV1,
                                            effect_receipt: EffectExecutionReceiptV1,
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
                                            runtime_key: bytes,
                                            effect_key: bytes) -> EffectExecutionProofEnvelopeV1:
    base.assert_valid(
        grant=grant, evidence=evidence, mir=mir, request=request, proof=proof,
        bound=bound, basis=basis, decision=decision, permit=permit,
        consumption=consumption, decision_key=decision_key, runtime_key=runtime_key,
    )
    effect_receipt.assert_authenticated(
        effect_key=effect_key, consumption=consumption, permit=permit,
        mir=mir, request=request,
    )
    result = EffectExecutionProofEnvelopeV1(
        base_execution_envelope_digest=base.envelope_digest,
        effect_receipt_digest=effect_receipt.receipt_digest,
        canonical_request_digest=request.digest,
        operation=request.operation,
        epoch=request.epoch,
        terminal_state=effect_receipt.outcome,
        measurement_digest=effect_receipt.measurement_digest,
        envelope_digest="",
    )
    object.__setattr__(result, "envelope_digest", _digest(base, effect_receipt))
    result.assert_valid(
        base=base, effect_receipt=effect_receipt, grant=grant, evidence=evidence,
        mir=mir, request=request, proof=proof, bound=bound, basis=basis,
        decision=decision, permit=permit, consumption=consumption,
        decision_key=decision_key, runtime_key=runtime_key, effect_key=effect_key,
    )
    return result
