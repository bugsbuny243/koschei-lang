"""Historical-integrity validation for external finality proof envelopes v1.

Historical integrity answers: "Was this exact proof chain internally authentic and bound
as issued?" It deliberately does NOT answer: "Is the verifier trust generation still
current under today's operational policy?" Current operational validation remains
`ExternalFinalityProofEnvelopeV1.assert_valid(...)`.

Witness-backed native receipts require the archived A/B witness evidence bundles so their
artifact/raw-response/challenge/proof seals can be rechecked without requiring current
witness liveness.
"""
from __future__ import annotations
from .external_finality_proof_envelope_v1 import ExternalFinalityProofEnvelopeV1,_digest
from .monotonic_witness_evidence_v1 import MonotonicWitnessEvidenceBundleV1
from .provider_native_historical_integrity_v1 import assert_provider_native_historical_integrity_v1

class ExternalFinalityHistoricalIntegrityV1Error(ValueError): pass

def assert_external_finality_historical_integrity_v1(*,envelope:ExternalFinalityProofEnvelopeV1,effect_envelope,effect_receipt,effect_result_bytes,raw_provider_response_bytes,adapter_abi,provenance,runtime_admission,reproducible_admission,reproducibility_receipt,reproducibility_key,verifier_artifact_bytes,build_provenance_key,runtime_admission_key,reproducible_admission_key,native_receipt,base,grant,evidence,mir,request,proof,bound,basis,decision,permit,consumption,verdict,attestation,decision_key,runtime_key,effect_key,provider_native_verifier_key,provider_verifier_key,finality_key,builder_a_witness_evidence:MonotonicWitnessEvidenceBundleV1|None=None,builder_b_witness_evidence:MonotonicWitnessEvidenceBundleV1|None=None,builder_a_witness_verifier_key:bytes|None=None,builder_b_witness_verifier_key:bytes|None=None)->None:
    if envelope.authority: raise ExternalFinalityHistoricalIntegrityV1Error("external finality proof envelope cannot carry ambient authority")
    if envelope.terminal_state not in {"provider-pending","provider-finalized","provider-rejected"}: raise ExternalFinalityHistoricalIntegrityV1Error("unknown external finality proof-envelope terminal state")
    effect_envelope.assert_valid(base=base,effect_receipt=effect_receipt,grant=grant,evidence=evidence,mir=mir,request=request,proof=proof,bound=bound,basis=basis,decision=decision,permit=permit,consumption=consumption,decision_key=decision_key,runtime_key=runtime_key,effect_key=effect_key)
    assert_provider_native_historical_integrity_v1(receipt=native_receipt,provider_native_verifier_key=provider_native_verifier_key,adapter_abi=adapter_abi,runtime_admission=runtime_admission,reproducible_admission=reproducible_admission,reproducibility_receipt=reproducibility_receipt,reproducibility_key=reproducibility_key,provenance=provenance,verifier_artifact_bytes=verifier_artifact_bytes,build_provenance_key=build_provenance_key,runtime_admission_key=runtime_admission_key,reproducible_admission_key=reproducible_admission_key,effect_envelope=effect_envelope,effect_receipt=effect_receipt,effect_result_bytes=effect_result_bytes,raw_response_bytes=raw_provider_response_bytes,builder_a_witness_evidence=builder_a_witness_evidence,builder_b_witness_evidence=builder_b_witness_evidence,builder_a_witness_verifier_key=builder_a_witness_verifier_key,builder_b_witness_verifier_key=builder_b_witness_verifier_key)
    verdict.assert_authenticated(provider_verifier_key=provider_verifier_key,effect_envelope=effect_envelope)
    attestation.assert_authenticated(provider_verifier_key=provider_verifier_key,finality_key=finality_key,effect_envelope=effect_envelope,verdict=verdict)
    for actual,expected,label in ((verdict.provider_id,native_receipt.provider_id,"native provider"),(verdict.external_reference_digest,native_receipt.verified_reference_digest,"native reference"),(verdict.provider_proof_digest,native_receipt.provider_proof_digest,"native proof"),(verdict.observed_epoch,native_receipt.observed_epoch,"native epoch"),(verdict.state,native_receipt.state,"native state")):
        if actual!=expected: raise ExternalFinalityHistoricalIntegrityV1Error(f"provider verdict {label} mismatch")
    expected_fields=((envelope.effect_execution_envelope_digest,effect_envelope.envelope_digest,"effect envelope"),(envelope.provider_adapter_abi_digest,adapter_abi.abi_digest,"adapter ABI"),(envelope.verifier_implementation_digest,adapter_abi.verifier_implementation_digest,"verifier implementation"),(envelope.verifier_build_provenance_digest,provenance.provenance_digest,"build provenance"),(envelope.verifier_runtime_admission_digest,runtime_admission.admission_digest,"runtime admission"),(envelope.verifier_reproducibility_receipt_digest,reproducible_admission.reproducibility_receipt_digest,"reproducibility receipt"),(envelope.verifier_reproducible_runtime_admission_digest,reproducible_admission.admission_digest,"reproducible runtime admission"),(envelope.provider_native_verification_receipt_digest,native_receipt.receipt_digest,"native verification receipt"),(envelope.raw_provider_response_digest,native_receipt.raw_response_digest,"raw provider response"),(envelope.provider_verdict_digest,verdict.verdict_digest,"provider verdict"),(envelope.finality_attestation_digest,attestation.attestation_digest,"finality attestation"),(envelope.provider_id,attestation.provider_id,"provider"),(envelope.external_reference_digest,attestation.external_reference_digest,"external reference"),(envelope.provider_proof_digest,attestation.provider_proof_digest,"provider proof"),(envelope.observed_epoch,attestation.observed_epoch,"observed epoch"),(envelope.terminal_state,attestation.terminal_state,"terminal state"))
    for actual,expected,label in expected_fields:
        if actual!=expected: raise ExternalFinalityHistoricalIntegrityV1Error(f"external finality proof-envelope {label} mismatch")
    expected_digest=_digest(effect_envelope=effect_envelope,adapter_abi=adapter_abi,provenance=provenance,runtime_admission=runtime_admission,reproducible_admission=reproducible_admission,native_receipt=native_receipt,verdict=verdict,attestation=attestation)
    if envelope.envelope_digest!=expected_digest: raise ExternalFinalityHistoricalIntegrityV1Error("external finality proof-envelope seal mismatch")

def assert_historical_finalized_v1(envelope:ExternalFinalityProofEnvelopeV1)->None:
    if envelope.terminal_state!="provider-finalized": raise ExternalFinalityHistoricalIntegrityV1Error("historical provider finality is not proven by the sealed terminal state")
