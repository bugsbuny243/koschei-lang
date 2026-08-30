"""Historical-integrity validation for provider-native verification receipts v1.

This validates the exact sealed provider verification lineage without asking whether the
builder trust-anchor generations are still current today. If the native receipt was
witness-backed, the archived witness evidence seals are also required and revalidated.
Historical integrity is audit evidence, not permission for a new operation.
"""
from __future__ import annotations
import hashlib,hmac
from .effect_execution_proof_envelope_v1 import EffectExecutionProofEnvelopeV1
from .effect_execution_receipt_v1 import EffectExecutionReceiptV1
from .monotonic_witness_evidence_v1 import MonotonicWitnessEvidenceBundleV1
from .provider_adapter_abi_v1 import ProviderAdapterAbiV1
from .provider_native_verifier_v1 import ProviderNativeVerificationReceiptV1,_STATES,_RAW_CTX,_REF_CTX,_payload
from .verifier_build_provenance_v1 import VerifierBuildProvenanceV1,VerifierRuntimeAdmissionV1
from .verifier_generation_guard_v1 import assert_reproducibility_integrity_v1
from .verifier_reproducible_admission_v1 import VerifierReproducibleRuntimeAdmissionV1
from .verifier_reproducible_build_v1 import VerifierReproducibleBuildReceiptV1

class ProviderNativeHistoricalIntegrityV1Error(ValueError): pass

def _key(v:bytes)->bytes:
    if not isinstance(v,bytes) or len(v)<32: raise ProviderNativeHistoricalIntegrityV1Error("provider_native_verifier_key must contain at least 32 bytes")
    return v
def _text(v:str,label:str)->str:
    if not isinstance(v,str) or not v.strip(): raise ProviderNativeHistoricalIntegrityV1Error(f"{label} cannot be empty")
    return v.strip()
def _epoch(v:int)->int:
    if not isinstance(v,int) or isinstance(v,bool) or v<0: raise ProviderNativeHistoricalIntegrityV1Error("observed_epoch must be a non-negative integer")
    return v
def _generation(v:int)->int:
    if not isinstance(v,int) or isinstance(v,bool) or v<0: raise ProviderNativeHistoricalIntegrityV1Error("trust-anchor generation must be a non-negative integer")
    return v
def _hash(ctx:bytes,value:bytes,label:str)->str:
    if not isinstance(value,bytes) or not value: raise ProviderNativeHistoricalIntegrityV1Error(f"{label} must be non-empty bytes")
    return hashlib.sha256(ctx+value).hexdigest()
def _assert_witness_history(*,digest:str,evidence:MonotonicWitnessEvidenceBundleV1|None,key:bytes|None,label:str)->None:
    if not digest:
        if evidence is not None or key is not None: raise ProviderNativeHistoricalIntegrityV1Error(f"unexpected {label} witness evidence for unwitnessed receipt")
        return
    if evidence is None or key is None: raise ProviderNativeHistoricalIntegrityV1Error(f"{label} witness evidence is required for witnessed historical validation")
    evidence.assert_integrity(witness_verifier_key=key)
    if evidence.receipt.receipt_digest!=digest: raise ProviderNativeHistoricalIntegrityV1Error(f"{label} witness receipt digest mismatch")

def assert_provider_native_historical_integrity_v1(*,receipt:ProviderNativeVerificationReceiptV1,provider_native_verifier_key:bytes,adapter_abi:ProviderAdapterAbiV1,runtime_admission:VerifierRuntimeAdmissionV1,reproducible_admission:VerifierReproducibleRuntimeAdmissionV1,reproducibility_receipt:VerifierReproducibleBuildReceiptV1,reproducibility_key:bytes,provenance:VerifierBuildProvenanceV1,verifier_artifact_bytes:bytes,build_provenance_key:bytes,runtime_admission_key:bytes,reproducible_admission_key:bytes,effect_envelope:EffectExecutionProofEnvelopeV1,effect_receipt:EffectExecutionReceiptV1,effect_result_bytes:bytes,raw_response_bytes:bytes,builder_a_witness_evidence:MonotonicWitnessEvidenceBundleV1|None=None,builder_b_witness_evidence:MonotonicWitnessEvidenceBundleV1|None=None,builder_a_witness_verifier_key:bytes|None=None,builder_b_witness_verifier_key:bytes|None=None)->None:
    key=_key(provider_native_verifier_key); adapter_abi.assert_sealed()
    runtime_admission.assert_authenticated(runtime_admission_key=runtime_admission_key,build_provenance_key=build_provenance_key,provenance=provenance,artifact_bytes=verifier_artifact_bytes,adapter_abi=adapter_abi)
    reproducible_admission.assert_authenticated(reproducible_admission_key=reproducible_admission_key,base_admission=runtime_admission,adapter_abi=adapter_abi)
    if reproducible_admission.reproducibility_receipt_digest!=reproducibility_receipt.receipt_digest: raise ProviderNativeHistoricalIntegrityV1Error("provider-native reproducibility receipt differs from runtime admission")
    assert_reproducibility_integrity_v1(receipt=reproducibility_receipt,reproducibility_key=reproducibility_key)
    if bool(receipt.builder_a_monotonic_witness_receipt_digest)!=bool(receipt.builder_b_monotonic_witness_receipt_digest): raise ProviderNativeHistoricalIntegrityV1Error("provider-native historical receipt has asymmetric witness provenance")
    _assert_witness_history(digest=receipt.builder_a_monotonic_witness_receipt_digest,evidence=builder_a_witness_evidence,key=builder_a_witness_verifier_key,label="builder A")
    _assert_witness_history(digest=receipt.builder_b_monotonic_witness_receipt_digest,evidence=builder_b_witness_evidence,key=builder_b_witness_verifier_key,label="builder B")
    if receipt.authority: raise ProviderNativeHistoricalIntegrityV1Error("provider-native verification receipt cannot carry ambient authority")
    if effect_envelope.terminal_state!="effect-completed": raise ProviderNativeHistoricalIntegrityV1Error("provider-native historical integrity requires effect-completed")
    effect_receipt.assert_completed_result(effect_result_bytes)
    expected_links=((receipt.provider_id,adapter_abi.provider_id,"provider"),(receipt.adapter_abi_digest,adapter_abi.abi_digest,"adapter ABI"),(receipt.verifier_implementation_digest,adapter_abi.verifier_implementation_digest,"verifier implementation"),(receipt.runtime_admission_digest,runtime_admission.admission_digest,"runtime admission"),(receipt.reproducibility_receipt_digest,reproducibility_receipt.receipt_digest,"reproducibility receipt"),(receipt.reproducible_runtime_admission_digest,reproducible_admission.admission_digest,"reproducible admission"),(receipt.builder_a_trust_anchor_id,reproducibility_receipt.builder_a_trust_anchor_id,"builder A trust anchor"),(receipt.builder_a_trust_anchor_generation,reproducibility_receipt.builder_a_trust_anchor_generation,"builder A generation"),(receipt.builder_a_trust_anchor_manifest_digest,reproducibility_receipt.builder_a_trust_anchor_manifest_digest,"builder A manifest"),(receipt.builder_b_trust_anchor_id,reproducibility_receipt.builder_b_trust_anchor_id,"builder B trust anchor"),(receipt.builder_b_trust_anchor_generation,reproducibility_receipt.builder_b_trust_anchor_generation,"builder B generation"),(receipt.builder_b_trust_anchor_manifest_digest,reproducibility_receipt.builder_b_trust_anchor_manifest_digest,"builder B manifest"),(receipt.effect_execution_envelope_digest,effect_envelope.envelope_digest,"effect envelope"),(receipt.effect_receipt_digest,effect_envelope.effect_receipt_digest,"effect receipt"),(receipt.effect_measurement_digest,effect_envelope.measurement_digest,"effect measurement"))
    for actual,expected,label in expected_links:
        if actual!=expected: raise ProviderNativeHistoricalIntegrityV1Error(f"provider-native receipt {label} mismatch")
    expected_reference=_hash(_REF_CTX,effect_result_bytes,"effect_result_bytes")
    if receipt.expected_reference_digest!=expected_reference or receipt.verified_reference_digest!=expected_reference: raise ProviderNativeHistoricalIntegrityV1Error("provider-native verified reference differs from effect result")
    if receipt.raw_response_digest!=_hash(_RAW_CTX,raw_response_bytes,"raw_response_bytes"): raise ProviderNativeHistoricalIntegrityV1Error("provider-native raw response mismatch")
    if receipt.state not in _STATES: raise ProviderNativeHistoricalIntegrityV1Error("unknown provider-native verification state")
    epoch=_epoch(receipt.observed_epoch)
    if epoch<effect_envelope.epoch: raise ProviderNativeHistoricalIntegrityV1Error("provider-native observation predates effect epoch")
    expected=hmac.new(key,_payload(provider_id=_text(receipt.provider_id,"provider_id"),adapter_abi_digest=receipt.adapter_abi_digest,verifier_implementation_digest=receipt.verifier_implementation_digest,runtime_admission_digest=receipt.runtime_admission_digest,reproducibility_receipt_digest=receipt.reproducibility_receipt_digest,reproducible_runtime_admission_digest=receipt.reproducible_runtime_admission_digest,builder_a_anchor=_text(receipt.builder_a_trust_anchor_id,"builder_a_trust_anchor_id"),builder_a_generation=_generation(receipt.builder_a_trust_anchor_generation),builder_a_manifest=_text(receipt.builder_a_trust_anchor_manifest_digest,"builder_a_trust_anchor_manifest_digest"),builder_a_monotonic_witness_receipt_digest=receipt.builder_a_monotonic_witness_receipt_digest,builder_b_anchor=_text(receipt.builder_b_trust_anchor_id,"builder_b_trust_anchor_id"),builder_b_generation=_generation(receipt.builder_b_trust_anchor_generation),builder_b_manifest=_text(receipt.builder_b_trust_anchor_manifest_digest,"builder_b_trust_anchor_manifest_digest"),builder_b_monotonic_witness_receipt_digest=receipt.builder_b_monotonic_witness_receipt_digest,effect_envelope_digest=receipt.effect_execution_envelope_digest,effect_receipt_digest=receipt.effect_receipt_digest,effect_measurement_digest=receipt.effect_measurement_digest,raw_response_digest=receipt.raw_response_digest,expected_reference_digest=receipt.expected_reference_digest,verified_reference_digest=receipt.verified_reference_digest,provider_proof_digest=receipt.provider_proof_digest,observed_epoch=epoch,state=receipt.state),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(receipt.receipt_digest,expected): raise ProviderNativeHistoricalIntegrityV1Error("provider-native verification receipt authentication failed")
