"""End-to-end external-finality provenance envelope for Koschei Lang v1."""
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
from .external_finality_attestation_v1 import ExternalFinalityAttestationV1, ExternalProviderFinalityVerdictV1
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_proof_pipeline_v1 import NativeSigilProofBundle
from .native_sigil_request_binding_v1 import CanonicalEffectRequest, RequestBoundProof
from .provider_adapter_abi_v1 import ProviderAdapterAbiV1
from .provider_native_verifier_v1 import ProviderNativeVerificationReceiptV1

_CTX=b"koschei.external-finality-proof-envelope/v1\x00"
_TERMINALS=frozenset({"provider-pending","provider-finalized","provider-rejected"})
class ExternalFinalityProofEnvelopeV1Error(ValueError): pass

def _digest(effect_envelope,native_receipt,verdict,attestation):
    rows=(f"effect_envelope={effect_envelope.envelope_digest}",f"adapter_abi={native_receipt.adapter_abi_digest}",f"verifier_implementation={native_receipt.verifier_implementation_digest}",f"native_verification_receipt={native_receipt.receipt_digest}",f"raw_response={native_receipt.raw_response_digest}",f"provider_verdict={verdict.verdict_digest}",f"finality_attestation={attestation.attestation_digest}",f"provider={attestation.provider_id}",f"external_reference={attestation.external_reference_digest}",f"provider_proof={attestation.provider_proof_digest}",f"observed_epoch={attestation.observed_epoch}",f"terminal={attestation.terminal_state}","authority=0")
    return hashlib.sha256(_CTX+"\n".join(rows).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class ExternalFinalityProofEnvelopeV1:
    effect_execution_envelope_digest:str; provider_adapter_abi_digest:str; verifier_implementation_digest:str; provider_native_verification_receipt_digest:str; raw_provider_response_digest:str; provider_verdict_digest:str; finality_attestation_digest:str; provider_id:str; external_reference_digest:str; provider_proof_digest:str; observed_epoch:int; terminal_state:str; envelope_digest:str; authority:bool=False; version:int=1
    def assert_valid(self,*,adapter_abi:ProviderAdapterAbiV1,effect_envelope:EffectExecutionProofEnvelopeV1,effect_receipt:EffectExecutionReceiptV1,effect_result_bytes:bytes,raw_provider_response_bytes:bytes,native_receipt:ProviderNativeVerificationReceiptV1,base:ExecutionProofEnvelopeV1,grant:ExternalAdapterGrantV1,evidence:ExternalAdapterEvidenceV1,mir:NativeSigilMir,request:CanonicalEffectRequest,proof:NativeSigilProofBundle,bound:RequestBoundProof,basis:CanonicalAuthorityBasisV1,decision:AuthorizationDecisionV1,permit:ExecutionPermitV1,consumption:ExecutionConsumptionReceiptV1,verdict:ExternalProviderFinalityVerdictV1,attestation:ExternalFinalityAttestationV1,decision_key:bytes,runtime_key:bytes,effect_key:bytes,provider_native_verifier_key:bytes,provider_verifier_key:bytes,finality_key:bytes)->None:
        if self.authority: raise ExternalFinalityProofEnvelopeV1Error("external finality proof envelope cannot carry ambient authority")
        if self.terminal_state not in _TERMINALS: raise ExternalFinalityProofEnvelopeV1Error("unknown external finality proof-envelope terminal state")
        adapter_abi.assert_sealed()
        effect_envelope.assert_valid(base=base,effect_receipt=effect_receipt,grant=grant,evidence=evidence,mir=mir,request=request,proof=proof,bound=bound,basis=basis,decision=decision,permit=permit,consumption=consumption,decision_key=decision_key,runtime_key=runtime_key,effect_key=effect_key)
        if effect_envelope.terminal_state!="effect-completed": raise ExternalFinalityProofEnvelopeV1Error("external finality proof requires a locally completed effect")
        native_receipt.assert_authenticated(provider_native_verifier_key=provider_native_verifier_key,adapter_abi=adapter_abi,effect_envelope=effect_envelope,effect_receipt=effect_receipt,effect_result_bytes=effect_result_bytes,raw_response_bytes=raw_provider_response_bytes)
        verdict.assert_authenticated(provider_verifier_key=provider_verifier_key,effect_envelope=effect_envelope)
        attestation.assert_authenticated(provider_verifier_key=provider_verifier_key,finality_key=finality_key,effect_envelope=effect_envelope,verdict=verdict)
        bridge=((verdict.provider_id,native_receipt.provider_id),(verdict.external_reference_digest,native_receipt.verified_reference_digest),(verdict.provider_proof_digest,native_receipt.provider_proof_digest),(verdict.observed_epoch,native_receipt.observed_epoch),(verdict.state,native_receipt.state))
        if any(a!=b for a,b in bridge): raise ExternalFinalityProofEnvelopeV1Error("provider verdict is not derived from native verification receipt")
        expected=((self.effect_execution_envelope_digest,effect_envelope.envelope_digest,"effect envelope"),(self.provider_adapter_abi_digest,adapter_abi.abi_digest,"adapter ABI"),(self.verifier_implementation_digest,adapter_abi.verifier_implementation_digest,"verifier implementation"),(self.provider_native_verification_receipt_digest,native_receipt.receipt_digest,"native verification receipt"),(self.raw_provider_response_digest,native_receipt.raw_response_digest,"raw provider response"),(self.provider_verdict_digest,verdict.verdict_digest,"provider verdict"),(self.finality_attestation_digest,attestation.attestation_digest,"finality attestation"),(self.provider_id,attestation.provider_id,"provider"),(self.external_reference_digest,attestation.external_reference_digest,"external reference"),(self.provider_proof_digest,attestation.provider_proof_digest,"provider proof"),(self.observed_epoch,attestation.observed_epoch,"observed epoch"),(self.terminal_state,attestation.terminal_state,"terminal state"))
        for a,b,label in expected:
            if a!=b: raise ExternalFinalityProofEnvelopeV1Error(f"external finality proof-envelope {label} mismatch")
        if self.envelope_digest!=_digest(effect_envelope,native_receipt,verdict,attestation): raise ExternalFinalityProofEnvelopeV1Error("external finality proof-envelope seal mismatch")
    def assert_finalized(self):
        if self.terminal_state!="provider-finalized": raise ExternalFinalityProofEnvelopeV1Error("external provider finality is not proven")

def seal_external_finality_proof_envelope_v1(*,adapter_abi:ProviderAdapterAbiV1,effect_envelope:EffectExecutionProofEnvelopeV1,effect_receipt:EffectExecutionReceiptV1,effect_result_bytes:bytes,raw_provider_response_bytes:bytes,native_receipt:ProviderNativeVerificationReceiptV1,base:ExecutionProofEnvelopeV1,grant:ExternalAdapterGrantV1,evidence:ExternalAdapterEvidenceV1,mir:NativeSigilMir,request:CanonicalEffectRequest,proof:NativeSigilProofBundle,bound:RequestBoundProof,basis:CanonicalAuthorityBasisV1,decision:AuthorizationDecisionV1,permit:ExecutionPermitV1,consumption:ExecutionConsumptionReceiptV1,verdict:ExternalProviderFinalityVerdictV1,attestation:ExternalFinalityAttestationV1,decision_key:bytes,runtime_key:bytes,effect_key:bytes,provider_native_verifier_key:bytes,provider_verifier_key:bytes,finality_key:bytes)->ExternalFinalityProofEnvelopeV1:
    result=ExternalFinalityProofEnvelopeV1(effect_envelope.envelope_digest,adapter_abi.abi_digest,adapter_abi.verifier_implementation_digest,native_receipt.receipt_digest,native_receipt.raw_response_digest,verdict.verdict_digest,attestation.attestation_digest,attestation.provider_id,attestation.external_reference_digest,attestation.provider_proof_digest,attestation.observed_epoch,attestation.terminal_state,"")
    object.__setattr__(result,"envelope_digest",_digest(effect_envelope,native_receipt,verdict,attestation))
    result.assert_valid(adapter_abi=adapter_abi,effect_envelope=effect_envelope,effect_receipt=effect_receipt,effect_result_bytes=effect_result_bytes,raw_provider_response_bytes=raw_provider_response_bytes,native_receipt=native_receipt,base=base,grant=grant,evidence=evidence,mir=mir,request=request,proof=proof,bound=bound,basis=basis,decision=decision,permit=permit,consumption=consumption,verdict=verdict,attestation=attestation,decision_key=decision_key,runtime_key=runtime_key,effect_key=effect_key,provider_native_verifier_key=provider_native_verifier_key,provider_verifier_key=provider_verifier_key,finality_key=finality_key)
    return result
