"""Provider-native raw-response verification boundary for Koschei Lang v1.

The verifier callback may run only after exact-artifact admission, reproducibility-gated
admission, and a compact current-generation check over the authenticated reproducibility
receipt. Provider SDK/network parsing remains outside generic Lang core.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,hmac
from typing import Callable
from .effect_execution_proof_envelope_v1 import EffectExecutionProofEnvelopeV1
from .effect_execution_receipt_v1 import EffectExecutionReceiptV1
from .provider_adapter_abi_v1 import ProviderAdapterAbiV1
from .trust_anchor_admission_v1 import TrustAnchorGenerationStateV1
from .verifier_build_provenance_v1 import VerifierBuildProvenanceV1,VerifierRuntimeAdmissionV1
from .verifier_generation_guard_v1 import assert_reproducibility_current_v1
from .verifier_reproducible_admission_v1 import VerifierReproducibleRuntimeAdmissionV1
from .verifier_reproducible_build_v1 import VerifierReproducibleBuildReceiptV1

_CTX=b"koschei.provider-native-verifier/v1\x00"; _RAW_CTX=b"koschei.provider-native-raw-response/v1\x00"; _REF_CTX=b"koschei.provider-native-reference/v1\x00"; _PROOF_CTX=b"koschei.provider-native-proof/v1\x00"; _STATES=frozenset({"pending","finalized","rejected"})
class ProviderNativeVerifierV1Error(ValueError): pass
def _key(value:bytes)->bytes:
    if not isinstance(value,bytes) or len(value)<32: raise ProviderNativeVerifierV1Error("provider_native_verifier_key must contain at least 32 bytes")
    return value
def _text(value:str,label:str)->str:
    if not isinstance(value,str) or not value.strip(): raise ProviderNativeVerifierV1Error(f"{label} cannot be empty")
    return value.strip()
def _epoch(value:int)->int:
    if not isinstance(value,int) or isinstance(value,bool) or value<0: raise ProviderNativeVerifierV1Error("observed_epoch must be a non-negative integer")
    return value
def _generation(value:int)->int:
    if not isinstance(value,int) or isinstance(value,bool) or value<0: raise ProviderNativeVerifierV1Error("trust-anchor generation must be a non-negative integer")
    return value
def _hash(ctx:bytes,value:bytes,label:str)->str:
    if not isinstance(value,bytes) or not value: raise ProviderNativeVerifierV1Error(f"{label} must be non-empty bytes")
    return hashlib.sha256(ctx+value).hexdigest()
def _payload(**v)->bytes:
    rows=(f"provider={v['provider_id']}",f"adapter_abi={v['adapter_abi_digest']}",f"verifier_implementation={v['verifier_implementation_digest']}",f"runtime_admission={v['runtime_admission_digest']}",f"reproducibility_receipt={v['reproducibility_receipt_digest']}",f"reproducible_runtime_admission={v['reproducible_runtime_admission_digest']}",f"builder_a_anchor={v['builder_a_anchor']}",f"builder_a_generation={v['builder_a_generation']}",f"builder_a_manifest={v['builder_a_manifest']}",f"builder_b_anchor={v['builder_b_anchor']}",f"builder_b_generation={v['builder_b_generation']}",f"builder_b_manifest={v['builder_b_manifest']}",f"effect_envelope={v['effect_envelope_digest']}",f"effect_receipt={v['effect_receipt_digest']}",f"effect_measurement={v['effect_measurement_digest']}",f"raw_response={v['raw_response_digest']}",f"expected_reference={v['expected_reference_digest']}",f"verified_reference={v['verified_reference_digest']}",f"provider_proof={v['provider_proof_digest']}",f"observed_epoch={v['observed_epoch']}",f"state={v['state']}","authority=0")
    return _CTX+"\n".join(rows).encode()
@dataclass(frozen=True,slots=True)
class ProviderNativeVerificationResultV1:
    reference_bytes:bytes; proof_bytes:bytes; state:str
@dataclass(frozen=True,slots=True)
class ProviderNativeVerificationReceiptV1:
    provider_id:str; adapter_abi_digest:str; verifier_implementation_digest:str; runtime_admission_digest:str; reproducibility_receipt_digest:str; reproducible_runtime_admission_digest:str
    builder_a_trust_anchor_id:str; builder_a_trust_anchor_generation:int; builder_a_trust_anchor_manifest_digest:str
    builder_b_trust_anchor_id:str; builder_b_trust_anchor_generation:int; builder_b_trust_anchor_manifest_digest:str
    effect_execution_envelope_digest:str; effect_receipt_digest:str; effect_measurement_digest:str; raw_response_digest:str; expected_reference_digest:str; verified_reference_digest:str; provider_proof_digest:str; observed_epoch:int; state:str; receipt_digest:str
    authority:bool=False; version:int=1
    def assert_authenticated(self,*,provider_native_verifier_key:bytes,adapter_abi:ProviderAdapterAbiV1,runtime_admission:VerifierRuntimeAdmissionV1,reproducible_admission:VerifierReproducibleRuntimeAdmissionV1,reproducibility_receipt:VerifierReproducibleBuildReceiptV1,reproducibility_key:bytes,builder_a_generation_state:TrustAnchorGenerationStateV1,builder_b_generation_state:TrustAnchorGenerationStateV1,provenance:VerifierBuildProvenanceV1,verifier_artifact_bytes:bytes,build_provenance_key:bytes,runtime_admission_key:bytes,reproducible_admission_key:bytes,effect_envelope:EffectExecutionProofEnvelopeV1,effect_receipt:EffectExecutionReceiptV1,effect_result_bytes:bytes,raw_response_bytes:bytes)->None:
        key=_key(provider_native_verifier_key); adapter_abi.assert_sealed()
        runtime_admission.assert_authenticated(runtime_admission_key=runtime_admission_key,build_provenance_key=build_provenance_key,provenance=provenance,artifact_bytes=verifier_artifact_bytes,adapter_abi=adapter_abi)
        reproducible_admission.assert_authenticated(reproducible_admission_key=reproducible_admission_key,base_admission=runtime_admission,adapter_abi=adapter_abi)
        if reproducible_admission.reproducibility_receipt_digest!=reproducibility_receipt.receipt_digest: raise ProviderNativeVerifierV1Error("provider-native reproducibility receipt differs from runtime admission")
        assert_reproducibility_current_v1(receipt=reproducibility_receipt,reproducibility_key=reproducibility_key,builder_a_generation_state=builder_a_generation_state,builder_b_generation_state=builder_b_generation_state)
        if self.authority: raise ProviderNativeVerifierV1Error("provider-native verification receipt cannot carry ambient authority")
        if effect_envelope.terminal_state!="effect-completed": raise ProviderNativeVerifierV1Error("provider-native verification requires effect-completed")
        effect_receipt.assert_completed_result(effect_result_bytes)
        expected_links=(
            (self.provider_id,adapter_abi.provider_id,"provider"),(self.adapter_abi_digest,adapter_abi.abi_digest,"adapter ABI"),(self.verifier_implementation_digest,adapter_abi.verifier_implementation_digest,"verifier implementation"),(self.runtime_admission_digest,runtime_admission.admission_digest,"runtime admission"),(self.reproducibility_receipt_digest,reproducibility_receipt.receipt_digest,"reproducibility receipt"),(self.reproducible_runtime_admission_digest,reproducible_admission.admission_digest,"reproducible admission"),
            (self.builder_a_trust_anchor_id,reproducibility_receipt.builder_a_trust_anchor_id,"builder A trust anchor"),(self.builder_a_trust_anchor_generation,reproducibility_receipt.builder_a_trust_anchor_generation,"builder A generation"),(self.builder_a_trust_anchor_manifest_digest,reproducibility_receipt.builder_a_trust_anchor_manifest_digest,"builder A manifest"),(self.builder_b_trust_anchor_id,reproducibility_receipt.builder_b_trust_anchor_id,"builder B trust anchor"),(self.builder_b_trust_anchor_generation,reproducibility_receipt.builder_b_trust_anchor_generation,"builder B generation"),(self.builder_b_trust_anchor_manifest_digest,reproducibility_receipt.builder_b_trust_anchor_manifest_digest,"builder B manifest"),
            (self.effect_execution_envelope_digest,effect_envelope.envelope_digest,"effect envelope"),(self.effect_receipt_digest,effect_envelope.effect_receipt_digest,"effect receipt"),(self.effect_measurement_digest,effect_envelope.measurement_digest,"effect measurement"),)
        for actual,expected,label in expected_links:
            if actual!=expected: raise ProviderNativeVerifierV1Error(f"provider-native receipt {label} mismatch")
        expected_reference=_hash(_REF_CTX,effect_result_bytes,"effect_result_bytes")
        if self.expected_reference_digest!=expected_reference or self.verified_reference_digest!=expected_reference: raise ProviderNativeVerifierV1Error("provider-native verified reference differs from effect result")
        if self.raw_response_digest!=_hash(_RAW_CTX,raw_response_bytes,"raw_response_bytes"): raise ProviderNativeVerifierV1Error("provider-native raw response mismatch")
        if self.state not in _STATES: raise ProviderNativeVerifierV1Error("unknown provider-native verification state")
        epoch=_epoch(self.observed_epoch)
        if epoch<effect_envelope.epoch: raise ProviderNativeVerifierV1Error("provider-native observation predates effect epoch")
        expected=hmac.new(key,_payload(provider_id=_text(self.provider_id,"provider_id"),adapter_abi_digest=self.adapter_abi_digest,verifier_implementation_digest=self.verifier_implementation_digest,runtime_admission_digest=self.runtime_admission_digest,reproducibility_receipt_digest=self.reproducibility_receipt_digest,reproducible_runtime_admission_digest=self.reproducible_runtime_admission_digest,builder_a_anchor=_text(self.builder_a_trust_anchor_id,"builder_a_trust_anchor_id"),builder_a_generation=_generation(self.builder_a_trust_anchor_generation),builder_a_manifest=_text(self.builder_a_trust_anchor_manifest_digest,"builder_a_trust_anchor_manifest_digest"),builder_b_anchor=_text(self.builder_b_trust_anchor_id,"builder_b_trust_anchor_id"),builder_b_generation=_generation(self.builder_b_trust_anchor_generation),builder_b_manifest=_text(self.builder_b_trust_anchor_manifest_digest,"builder_b_trust_anchor_manifest_digest"),effect_envelope_digest=self.effect_execution_envelope_digest,effect_receipt_digest=self.effect_receipt_digest,effect_measurement_digest=self.effect_measurement_digest,raw_response_digest=self.raw_response_digest,expected_reference_digest=self.expected_reference_digest,verified_reference_digest=self.verified_reference_digest,provider_proof_digest=self.provider_proof_digest,observed_epoch=epoch,state=self.state),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.receipt_digest,expected): raise ProviderNativeVerifierV1Error("provider-native verification receipt authentication failed")
def verify_provider_native_response_v1(*,provider_id:str,adapter_abi:ProviderAdapterAbiV1,runtime_admission:VerifierRuntimeAdmissionV1,reproducible_admission:VerifierReproducibleRuntimeAdmissionV1,reproducibility_receipt:VerifierReproducibleBuildReceiptV1,reproducibility_key:bytes,builder_a_generation_state:TrustAnchorGenerationStateV1,builder_b_generation_state:TrustAnchorGenerationStateV1,provenance:VerifierBuildProvenanceV1,verifier_artifact_bytes:bytes,build_provenance_key:bytes,runtime_admission_key:bytes,reproducible_admission_key:bytes,effect_envelope:EffectExecutionProofEnvelopeV1,effect_receipt:EffectExecutionReceiptV1,effect_result_bytes:bytes,raw_response_bytes:bytes,observed_epoch:int,verifier:Callable[[bytes],ProviderNativeVerificationResultV1],provider_native_verifier_key:bytes)->ProviderNativeVerificationReceiptV1:
    key=_key(provider_native_verifier_key); adapter_abi.assert_sealed()
    runtime_admission.assert_authenticated(runtime_admission_key=runtime_admission_key,build_provenance_key=build_provenance_key,provenance=provenance,artifact_bytes=verifier_artifact_bytes,adapter_abi=adapter_abi)
    reproducible_admission.assert_authenticated(reproducible_admission_key=reproducible_admission_key,base_admission=runtime_admission,adapter_abi=adapter_abi)
    if reproducible_admission.reproducibility_receipt_digest!=reproducibility_receipt.receipt_digest: raise ProviderNativeVerifierV1Error("provider-native reproducibility receipt differs from runtime admission")
    assert_reproducibility_current_v1(receipt=reproducibility_receipt,reproducibility_key=reproducibility_key,builder_a_generation_state=builder_a_generation_state,builder_b_generation_state=builder_b_generation_state)
    provider=_text(provider_id,"provider_id")
    if provider!=adapter_abi.provider_id: raise ProviderNativeVerifierV1Error("provider id differs from adapter ABI")
    epoch=_epoch(observed_epoch)
    if effect_envelope.terminal_state!="effect-completed": raise ProviderNativeVerifierV1Error("provider-native verification requires effect-completed")
    effect_receipt.assert_completed_result(effect_result_bytes)
    if not callable(verifier): raise ProviderNativeVerifierV1Error("provider-native verifier must be callable")
    raw_digest=_hash(_RAW_CTX,raw_response_bytes,"raw_response_bytes"); expected_reference=_hash(_REF_CTX,effect_result_bytes,"effect_result_bytes")
    if epoch<effect_envelope.epoch: raise ProviderNativeVerifierV1Error("provider-native observation predates effect epoch")
    result=verifier(raw_response_bytes)
    if not isinstance(result,ProviderNativeVerificationResultV1): raise ProviderNativeVerifierV1Error("provider-native verifier returned invalid result type")
    state=_text(result.state,"state")
    if state not in _STATES: raise ProviderNativeVerifierV1Error("unknown provider-native verification state")
    verified_reference=_hash(_REF_CTX,result.reference_bytes,"verified reference")
    if verified_reference!=expected_reference: raise ProviderNativeVerifierV1Error("provider-native verified reference differs from effect result")
    provider_proof=_hash(_PROOF_CTX,result.proof_bytes,"provider proof")
    receipt=ProviderNativeVerificationReceiptV1(provider,adapter_abi.abi_digest,adapter_abi.verifier_implementation_digest,runtime_admission.admission_digest,reproducibility_receipt.receipt_digest,reproducible_admission.admission_digest,reproducibility_receipt.builder_a_trust_anchor_id,reproducibility_receipt.builder_a_trust_anchor_generation,reproducibility_receipt.builder_a_trust_anchor_manifest_digest,reproducibility_receipt.builder_b_trust_anchor_id,reproducibility_receipt.builder_b_trust_anchor_generation,reproducibility_receipt.builder_b_trust_anchor_manifest_digest,effect_envelope.envelope_digest,effect_envelope.effect_receipt_digest,effect_envelope.measurement_digest,raw_digest,expected_reference,verified_reference,provider_proof,epoch,state,"")
    object.__setattr__(receipt,"receipt_digest",hmac.new(key,_payload(provider_id=receipt.provider_id,adapter_abi_digest=receipt.adapter_abi_digest,verifier_implementation_digest=receipt.verifier_implementation_digest,runtime_admission_digest=receipt.runtime_admission_digest,reproducibility_receipt_digest=receipt.reproducibility_receipt_digest,reproducible_runtime_admission_digest=receipt.reproducible_runtime_admission_digest,builder_a_anchor=receipt.builder_a_trust_anchor_id,builder_a_generation=receipt.builder_a_trust_anchor_generation,builder_a_manifest=receipt.builder_a_trust_anchor_manifest_digest,builder_b_anchor=receipt.builder_b_trust_anchor_id,builder_b_generation=receipt.builder_b_trust_anchor_generation,builder_b_manifest=receipt.builder_b_trust_anchor_manifest_digest,effect_envelope_digest=receipt.effect_execution_envelope_digest,effect_receipt_digest=receipt.effect_receipt_digest,effect_measurement_digest=receipt.effect_measurement_digest,raw_response_digest=receipt.raw_response_digest,expected_reference_digest=receipt.expected_reference_digest,verified_reference_digest=receipt.verified_reference_digest,provider_proof_digest=receipt.provider_proof_digest,observed_epoch=receipt.observed_epoch,state=receipt.state),hashlib.sha256).hexdigest())
    receipt.assert_authenticated(provider_native_verifier_key=key,adapter_abi=adapter_abi,runtime_admission=runtime_admission,reproducible_admission=reproducible_admission,reproducibility_receipt=reproducibility_receipt,reproducibility_key=reproducibility_key,builder_a_generation_state=builder_a_generation_state,builder_b_generation_state=builder_b_generation_state,provenance=provenance,verifier_artifact_bytes=verifier_artifact_bytes,build_provenance_key=build_provenance_key,runtime_admission_key=runtime_admission_key,reproducible_admission_key=reproducible_admission_key,effect_envelope=effect_envelope,effect_receipt=effect_receipt,effect_result_bytes=effect_result_bytes,raw_response_bytes=raw_response_bytes)
    return receipt
