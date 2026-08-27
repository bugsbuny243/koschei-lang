"""End-to-end external-finality provenance envelope for Koschei Lang v1.

A provider verdict or finality attestation is not sufficient by itself.  This module
re-verifies the complete effect-execution provenance chain plus both finality trust
roles before exposing `provider-finalized`, `provider-rejected`, or `provider-pending`.

The envelope carries no authority and is never a capability.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .authorization_decision_v1 import AuthorizationDecisionV1
from .canonical_authority_basis_v1 import CanonicalAuthorityBasisV1
from .effect_execution_proof_envelope_v1 import EffectExecutionProofEnvelopeV1
from .effect_execution_receipt_v1 import EffectExecutionReceiptV1
from .execution_permit_v1 import ExecutionConsumptionReceiptV1, ExecutionPermitV1
from .execution_proof_envelope_v1 import ExecutionProofEnvelopeV1
from .external_adapter_contract_v1 import ExternalAdapterEvidenceV1, ExternalAdapterGrantV1
from .external_finality_attestation_v1 import (
    ExternalFinalityAttestationV1,
    ExternalProviderFinalityVerdictV1,
)
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_proof_pipeline_v1 import NativeSigilProofBundle
from .native_sigil_request_binding_v1 import CanonicalEffectRequest, RequestBoundProof

_CTX = b"koschei.external-finality-proof-envelope/v1\x00"
_TERMINALS = frozenset({"provider-pending", "provider-finalized", "provider-rejected"})


class ExternalFinalityProofEnvelopeV1Error(ValueError):
    pass


def _digest(*, effect_envelope: EffectExecutionProofEnvelopeV1,
            verdict: ExternalProviderFinalityVerdictV1,
            attestation: ExternalFinalityAttestationV1) -> str:
    rows = (
        f"effect_envelope={effect_envelope.envelope_digest}",
        f"provider_verdict={verdict.verdict_digest}",
        f"finality_attestation={attestation.attestation_digest}",
        f"provider={attestation.provider_id}",
        f"external_reference={attestation.external_reference_digest}",
        f"provider_proof={attestation.provider_proof_digest}",
        f"observed_epoch={attestation.observed_epoch}",
        f"terminal={attestation.terminal_state}",
        "authority=0",
    )
    return hashlib.sha256(_CTX + "\n".join(rows).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ExternalFinalityProofEnvelopeV1:
    effect_execution_envelope_digest: str
    provider_verdict_digest: str
    finality_attestation_digest: str
    provider_id: str
    external_reference_digest: str
    provider_proof_digest: str
    observed_epoch: int
    terminal_state: str
    envelope_digest: str
    authority: bool = False
    version: int = 1

    def assert_valid(self, *,
                     effect_envelope: EffectExecutionProofEnvelopeV1,
                     effect_receipt: EffectExecutionReceiptV1,
                     base: ExecutionProofEnvelopeV1,
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
                     verdict: ExternalProviderFinalityVerdictV1,
                     attestation: ExternalFinalityAttestationV1,
                     decision_key: bytes,
                     runtime_key: bytes,
                     effect_key: bytes,
                     provider_verifier_key: bytes,
                     finality_key: bytes) -> None:
        if self.authority:
            raise ExternalFinalityProofEnvelopeV1Error("external finality proof envelope cannot carry ambient authority")
        if self.terminal_state not in _TERMINALS:
            raise ExternalFinalityProofEnvelopeV1Error("unknown external finality proof-envelope terminal state")
        effect_envelope.assert_valid(
            base=base,
            effect_receipt=effect_receipt,
            grant=grant,
            evidence=evidence,
            mir=mir,
            request=request,
            proof=proof,
            bound=bound,
            basis=basis,
            decision=decision,
            permit=permit,
            consumption=consumption,
            decision_key=decision_key,
            runtime_key=runtime_key,
            effect_key=effect_key,
        )
        if effect_envelope.terminal_state != "effect-completed":
            raise ExternalFinalityProofEnvelopeV1Error(
                "external finality proof requires a locally completed effect"
            )
        verdict.assert_authenticated(
            provider_verifier_key=provider_verifier_key,
            effect_envelope=effect_envelope,
        )
        attestation.assert_authenticated(
            provider_verifier_key=provider_verifier_key,
            finality_key=finality_key,
            effect_envelope=effect_envelope,
            verdict=verdict,
        )
        expected_fields = (
            (self.effect_execution_envelope_digest, effect_envelope.envelope_digest, "effect envelope"),
            (self.provider_verdict_digest, verdict.verdict_digest, "provider verdict"),
            (self.finality_attestation_digest, attestation.attestation_digest, "finality attestation"),
            (self.provider_id, attestation.provider_id, "provider"),
            (self.external_reference_digest, attestation.external_reference_digest, "external reference"),
            (self.provider_proof_digest, attestation.provider_proof_digest, "provider proof"),
            (self.observed_epoch, attestation.observed_epoch, "observed epoch"),
            (self.terminal_state, attestation.terminal_state, "terminal state"),
        )
        for actual, expected, label in expected_fields:
            if actual != expected:
                raise ExternalFinalityProofEnvelopeV1Error(
                    f"external finality proof-envelope {label} mismatch"
                )
        if self.envelope_digest != _digest(
            effect_envelope=effect_envelope,
            verdict=verdict,
            attestation=attestation,
        ):
            raise ExternalFinalityProofEnvelopeV1Error("external finality proof-envelope seal mismatch")

    def assert_finalized(self) -> None:
        if self.terminal_state != "provider-finalized":
            raise ExternalFinalityProofEnvelopeV1Error("external provider finality is not proven")


def seal_external_finality_proof_envelope_v1(*,
                                             effect_envelope: EffectExecutionProofEnvelopeV1,
                                             effect_receipt: EffectExecutionReceiptV1,
                                             base: ExecutionProofEnvelopeV1,
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
                                             verdict: ExternalProviderFinalityVerdictV1,
                                             attestation: ExternalFinalityAttestationV1,
                                             decision_key: bytes,
                                             runtime_key: bytes,
                                             effect_key: bytes,
                                             provider_verifier_key: bytes,
                                             finality_key: bytes) -> ExternalFinalityProofEnvelopeV1:
    """Seal finality provenance only after the entire prior execution chain re-verifies."""
    effect_envelope.assert_valid(
        base=base,
        effect_receipt=effect_receipt,
        grant=grant,
        evidence=evidence,
        mir=mir,
        request=request,
        proof=proof,
        bound=bound,
        basis=basis,
        decision=decision,
        permit=permit,
        consumption=consumption,
        decision_key=decision_key,
        runtime_key=runtime_key,
        effect_key=effect_key,
    )
    if effect_envelope.terminal_state != "effect-completed":
        raise ExternalFinalityProofEnvelopeV1Error(
            "external finality proof requires a locally completed effect"
        )
    verdict.assert_authenticated(
        provider_verifier_key=provider_verifier_key,
        effect_envelope=effect_envelope,
    )
    attestation.assert_authenticated(
        provider_verifier_key=provider_verifier_key,
        finality_key=finality_key,
        effect_envelope=effect_envelope,
        verdict=verdict,
    )
    result = ExternalFinalityProofEnvelopeV1(
        effect_execution_envelope_digest=effect_envelope.envelope_digest,
        provider_verdict_digest=verdict.verdict_digest,
        finality_attestation_digest=attestation.attestation_digest,
        provider_id=attestation.provider_id,
        external_reference_digest=attestation.external_reference_digest,
        provider_proof_digest=attestation.provider_proof_digest,
        observed_epoch=attestation.observed_epoch,
        terminal_state=attestation.terminal_state,
        envelope_digest="",
    )
    object.__setattr__(result, "envelope_digest", _digest(
        effect_envelope=effect_envelope,
        verdict=verdict,
        attestation=attestation,
    ))
    result.assert_valid(
        effect_envelope=effect_envelope,
        effect_receipt=effect_receipt,
        base=base,
        grant=grant,
        evidence=evidence,
        mir=mir,
        request=request,
        proof=proof,
        bound=bound,
        basis=basis,
        decision=decision,
        permit=permit,
        consumption=consumption,
        verdict=verdict,
        attestation=attestation,
        decision_key=decision_key,
        runtime_key=runtime_key,
        effect_key=effect_key,
        provider_verifier_key=provider_verifier_key,
        finality_key=finality_key,
    )
    return result
