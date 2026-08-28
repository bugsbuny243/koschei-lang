"""Reproducibility-gated verifier runtime admission for Koschei Lang v1."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,hmac
from .provider_adapter_abi_v1 import ProviderAdapterAbiV1
from .verifier_build_provenance_v1 import VerifierRuntimeAdmissionV1,admit_verifier_artifact_v1
_CTX=b"koschei.verifier-reproducible-runtime-admission/v1\x00"
class VerifierReproducibleAdmissionV1Error(ValueError): pass
def _key(v):
    if not isinstance(v,bytes) or len(v)<32: raise VerifierReproducibleAdmissionV1Error("reproducible_admission_key must contain at least 32 bytes")
    return v
def _text(v,label):
    if not isinstance(v,str) or not v.strip(): raise VerifierReproducibleAdmissionV1Error(f"{label} cannot be empty")
    return v.strip()
def _policy(v):
    if not isinstance(v,bool): raise VerifierReproducibleAdmissionV1Error("require_distinct_trust_roots must be boolean")
    return v
def _payload(*,base_admission_digest,reproducibility_receipt_digest,verified_input_digest,artifact_digest,adapter_abi_digest,builder_a_trust_root_id,builder_b_trust_root_id,require_distinct_trust_roots):
    return _CTX+"\n".join((f"base_admission={base_admission_digest}",f"reproducibility={reproducibility_receipt_digest}",f"verified_input={verified_input_digest}",f"artifact={artifact_digest}",f"abi={adapter_abi_digest}",f"builder_a_root={builder_a_trust_root_id}",f"builder_b_root={builder_b_trust_root_id}",f"require_distinct_trust_roots={1 if require_distinct_trust_roots else 0}","admitted=1","authority=0")).encode()
@dataclass(frozen=True,slots=True)
class VerifierReproducibleRuntimeAdmissionV1:
    base_runtime_admission_digest:str; reproducibility_receipt_digest:str; verified_input_digest:str; artifact_digest:str; provider_adapter_abi_digest:str; builder_a_trust_root_id:str; builder_b_trust_root_id:str; require_distinct_trust_roots:bool; admission_digest:str; admitted:bool=True; authority:bool=False; version:int=1
    def assert_authenticated(self,*,reproducible_admission_key,base_admission:VerifierRuntimeAdmissionV1,adapter_abi:ProviderAdapterAbiV1):
        key=_key(reproducible_admission_key); adapter_abi.assert_sealed(); policy=_policy(self.require_distinct_trust_roots); root_a=_text(self.builder_a_trust_root_id,"builder_a_trust_root_id"); root_b=_text(self.builder_b_trust_root_id,"builder_b_trust_root_id")
        if self.authority or self.admitted is not True: raise VerifierReproducibleAdmissionV1Error("reproducible runtime admission must remain non-authoritative and admitted")
        if policy and root_a==root_b: raise VerifierReproducibleAdmissionV1Error("reproducible admission distinct-root policy is violated")
        if self.base_runtime_admission_digest!=base_admission.admission_digest: raise VerifierReproducibleAdmissionV1Error("reproducible admission base runtime admission mismatch")
        if self.artifact_digest!=base_admission.artifact_digest: raise VerifierReproducibleAdmissionV1Error("reproducible admission artifact mismatch")
        if self.provider_adapter_abi_digest!=adapter_abi.abi_digest: raise VerifierReproducibleAdmissionV1Error("reproducible admission adapter ABI mismatch")
        expected=hmac.new(key,_payload(base_admission_digest=self.base_runtime_admission_digest,reproducibility_receipt_digest=self.reproducibility_receipt_digest,verified_input_digest=self.verified_input_digest,artifact_digest=self.artifact_digest,adapter_abi_digest=self.provider_adapter_abi_digest,builder_a_trust_root_id=root_a,builder_b_trust_root_id=root_b,require_distinct_trust_roots=policy),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.admission_digest,expected): raise VerifierReproducibleAdmissionV1Error("reproducible runtime admission authentication failed")
def admit_reproducible_verifier_artifact_v1(**k):
    receipt_args={name:k[name] for name in ('reproducibility_key','builder_a_key','builder_b_key','builder_a','builder_b','builder_a_toolchain','builder_b_toolchain','builder_a_toolchain_artifact_bytes','builder_b_toolchain_artifact_bytes','builder_a_toolchain_signing_key','builder_b_toolchain_signing_key','builder_a_environment','builder_b_environment','builder_a_environment_bytes','builder_b_environment_bytes','builder_a_workload_bytes','builder_b_workload_bytes','builder_a_environment_attestation_key','builder_b_environment_attestation_key','builder_a_remote_evidence','builder_b_remote_evidence','builder_a_raw_remote_evidence_bytes','builder_b_raw_remote_evidence_bytes','builder_a_remote_attestation_verifier_key','builder_b_remote_attestation_verifier_key','builder_a_trust_anchor_generation_state','builder_b_trust_anchor_generation_state','current_epoch','verified_input','mir','proof','artifact_bytes')}
    receipt_args['require_distinct_trust_roots']=k.get('require_distinct_trust_roots',False)
    receipt=k['reproducibility_receipt']; receipt.assert_authenticated(**receipt_args)
    k['provenance'].assert_from_verified_ir(verified_input=k['verified_input'],mir=k['mir'],proof=k['proof'],toolchain=k['build_toolchain'],toolchain_artifact_bytes=k['build_toolchain_artifact_bytes'],toolchain_signing_key=k['build_toolchain_signing_key'],build_provenance_key=k['build_provenance_key'],artifact_bytes=k['artifact_bytes'])
    if k['provenance'].toolchain_digest not in {k['builder_a'].toolchain_provenance_digest,k['builder_b'].toolchain_provenance_digest}: raise VerifierReproducibleAdmissionV1Error("build provenance toolchain is absent from reproducible builder observations")
    base=admit_verifier_artifact_v1(provenance=k['provenance'],artifact_bytes=k['artifact_bytes'],adapter_abi=k['adapter_abi'],build_provenance_key=k['build_provenance_key'],runtime_admission_key=k['runtime_admission_key'])
    if receipt.artifact_digest!=base.artifact_digest: raise VerifierReproducibleAdmissionV1Error("reproducible artifact differs from runtime-admitted artifact")
    key=_key(k['reproducible_admission_key']); result=VerifierReproducibleRuntimeAdmissionV1(base.admission_digest,receipt.receipt_digest,k['verified_input'].build_input_digest,base.artifact_digest,k['adapter_abi'].abi_digest,receipt.builder_a_trust_root_id,receipt.builder_b_trust_root_id,receipt.require_distinct_trust_roots,"")
    object.__setattr__(result,'admission_digest',hmac.new(key,_payload(base_admission_digest=result.base_runtime_admission_digest,reproducibility_receipt_digest=result.reproducibility_receipt_digest,verified_input_digest=result.verified_input_digest,artifact_digest=result.artifact_digest,adapter_abi_digest=result.provider_adapter_abi_digest,builder_a_trust_root_id=result.builder_a_trust_root_id,builder_b_trust_root_id=result.builder_b_trust_root_id,require_distinct_trust_roots=result.require_distinct_trust_roots),hashlib.sha256).hexdigest())
    result.assert_authenticated(reproducible_admission_key=key,base_admission=base,adapter_abi=k['adapter_abi'])
    return base,result
