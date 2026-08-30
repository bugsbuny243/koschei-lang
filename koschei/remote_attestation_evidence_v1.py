"""Provider-neutral remote attestation evidence for Koschei Lang v1.

Sanctioned issuance requires a non-recursive trust-anchor admission for the exact
attestation-verifier artifact and the currently observed trust-anchor generation before
provider-specific parsing can execute. The root-authenticated manifest lifetime is copied
into the authenticated evidence and bounds the provider-returned evidence lifetime.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,hmac
from .attestation_verifier_abi_v1 import AttestationVerifierAbiV1,measure_attestation_verifier_artifact_v1
from .trust_anchor_admission_v1 import TrustAnchorGenerationStateV1,TrustAnchorManifestV1,TrustAnchorRuntimeAdmissionV1

_CTX=b"koschei.remote-attestation-evidence/v1\x00"; _RAW_CTX=b"koschei.remote-attestation-raw/v1\x00"; _ENV_CTX=b"koschei.builder-environment-measurement/v1\x00"; _WORKLOAD_CTX=b"koschei.builder-workload-measurement/v1\x00"
class RemoteAttestationEvidenceV1Error(ValueError): pass
def _key(v:bytes)->bytes:
    if not isinstance(v,bytes) or len(v)<32: raise RemoteAttestationEvidenceV1Error("remote_attestation_verifier_key must contain at least 32 bytes")
    return v
def _text(v:str,label:str)->str:
    if not isinstance(v,str) or not v.strip(): raise RemoteAttestationEvidenceV1Error(f"{label} cannot be empty")
    return v.strip()
def _epoch(v:int)->int:
    if not isinstance(v,int) or isinstance(v,bool) or v<0: raise RemoteAttestationEvidenceV1Error("epoch must be a non-negative integer")
    return v
def _generation(v:int)->int:
    if not isinstance(v,int) or isinstance(v,bool) or v<0: raise RemoteAttestationEvidenceV1Error("generation must be a non-negative integer")
    return v
def measure_raw_remote_attestation_v1(raw_evidence_bytes:bytes)->str:
    if not isinstance(raw_evidence_bytes,bytes) or not raw_evidence_bytes: raise RemoteAttestationEvidenceV1Error("raw_evidence_bytes must be non-empty bytes")
    return hashlib.sha256(_RAW_CTX+raw_evidence_bytes).hexdigest()
def _measure_env(v:bytes)->str:
    if not isinstance(v,bytes) or not v: raise RemoteAttestationEvidenceV1Error("environment_bytes must be non-empty bytes")
    return hashlib.sha256(_ENV_CTX+v).hexdigest()
def _measure_workload(v:bytes)->str:
    if not isinstance(v,bytes) or not v: raise RemoteAttestationEvidenceV1Error("workload_bytes must be non-empty bytes")
    return hashlib.sha256(_WORKLOAD_CTX+v).hexdigest()
def _payload(**v)->bytes:
    rows=(f"provider={v['provider_id']}",f"trust_root={v['trust_root_id']}",f"raw={v['raw_evidence_digest']}",f"environment={v['environment_digest']}",f"workload={v['workload_digest']}",f"observed_epoch={v['observed_epoch']}",f"expires_before_epoch={v['expires_before_epoch']}",f"verifier_abi={v['verifier_abi_digest']}",f"verifier_implementation={v['verifier_implementation_digest']}",f"trust_anchor_id={v['trust_anchor_id']}",f"trust_anchor_generation={v['trust_anchor_generation']}",f"trust_anchor_manifest={v['trust_anchor_manifest_digest']}",f"trust_anchor_valid_from={v['trust_anchor_valid_from_epoch']}",f"trust_anchor_expires_before={v['trust_anchor_expires_before_epoch']}",f"trust_anchor_admission={v['trust_anchor_admission_digest']}","verified=1","authority=0")
    return _CTX+"\n".join(rows).encode()
@dataclass(frozen=True,slots=True)
class RemoteAttestationVerificationResultV1:
    trust_root_id:str; environment_bytes:bytes; workload_bytes:bytes; observed_epoch:int; expires_before_epoch:int
@dataclass(frozen=True,slots=True)
class RemoteAttestationEvidenceV1:
    provider_id:str; trust_root_id:str; raw_evidence_digest:str; environment_digest:str; workload_digest:str; observed_epoch:int; expires_before_epoch:int; attestation_verifier_abi_digest:str; verifier_implementation_digest:str; trust_anchor_id:str; trust_anchor_generation:int; trust_anchor_manifest_digest:str; trust_anchor_valid_from_epoch:int; trust_anchor_expires_before_epoch:int; trust_anchor_runtime_admission_digest:str; evidence_digest:str; verified:bool=True; authority:bool=False; version:int=1
    def assert_current_generation(self,*,trust_anchor_generation_state:TrustAnchorGenerationStateV1)->None:
        trust_anchor_generation_state.assert_current_binding(anchor_id=self.trust_anchor_id,generation=self.trust_anchor_generation,manifest_digest=self.trust_anchor_manifest_digest)
    def assert_authenticated(self,*,remote_attestation_verifier_key:bytes,raw_evidence_bytes:bytes,current_epoch:int)->None:
        key=_key(remote_attestation_verifier_key); current=_epoch(current_epoch)
        if self.authority or self.verified is not True: raise RemoteAttestationEvidenceV1Error("remote attestation evidence must remain verified and non-authoritative")
        if self.raw_evidence_digest!=measure_raw_remote_attestation_v1(raw_evidence_bytes): raise RemoteAttestationEvidenceV1Error("remote attestation raw evidence mismatch")
        observed=_epoch(self.observed_epoch); expires=_epoch(self.expires_before_epoch); generation=_generation(self.trust_anchor_generation); anchor_start=_epoch(self.trust_anchor_valid_from_epoch); anchor_end=_epoch(self.trust_anchor_expires_before_epoch)
        if anchor_end<=anchor_start: raise RemoteAttestationEvidenceV1Error("trust-anchor lifetime is invalid")
        if expires<=observed: raise RemoteAttestationEvidenceV1Error("remote attestation expiry must be after observed epoch")
        if observed<anchor_start or observed>=anchor_end: raise RemoteAttestationEvidenceV1Error("remote attestation observation is outside trust-anchor lifetime")
        if expires>anchor_end: raise RemoteAttestationEvidenceV1Error("remote attestation lifetime exceeds trust-anchor lifetime")
        if current<observed: raise RemoteAttestationEvidenceV1Error("remote attestation evidence is from the future")
        if current>=expires: raise RemoteAttestationEvidenceV1Error("remote attestation evidence is stale")
        expected=hmac.new(key,_payload(provider_id=_text(self.provider_id,"provider_id"),trust_root_id=_text(self.trust_root_id,"trust_root_id"),raw_evidence_digest=self.raw_evidence_digest,environment_digest=_text(self.environment_digest,"environment_digest"),workload_digest=_text(self.workload_digest,"workload_digest"),observed_epoch=observed,expires_before_epoch=expires,verifier_abi_digest=_text(self.attestation_verifier_abi_digest,"attestation_verifier_abi_digest"),verifier_implementation_digest=_text(self.verifier_implementation_digest,"verifier_implementation_digest"),trust_anchor_id=_text(self.trust_anchor_id,"trust_anchor_id"),trust_anchor_generation=generation,trust_anchor_manifest_digest=_text(self.trust_anchor_manifest_digest,"trust_anchor_manifest_digest"),trust_anchor_valid_from_epoch=anchor_start,trust_anchor_expires_before_epoch=anchor_end,trust_anchor_admission_digest=_text(self.trust_anchor_runtime_admission_digest,"trust_anchor_admission_digest")),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.evidence_digest,expected): raise RemoteAttestationEvidenceV1Error("remote attestation evidence authentication failed")
def _seal(**v):
    key=_key(v['remote_attestation_verifier_key']); observed=_epoch(v['observed_epoch']); expires=_epoch(v['expires_before_epoch']); generation=_generation(v['trust_anchor_generation']); anchor_start=_epoch(v['trust_anchor_valid_from_epoch']); anchor_end=_epoch(v['trust_anchor_expires_before_epoch'])
    if anchor_end<=anchor_start: raise RemoteAttestationEvidenceV1Error("trust-anchor lifetime is invalid")
    if expires<=observed: raise RemoteAttestationEvidenceV1Error("remote attestation expiry must be after observed epoch")
    if observed<anchor_start or observed>=anchor_end: raise RemoteAttestationEvidenceV1Error("remote attestation observation is outside trust-anchor lifetime")
    if expires>anchor_end: raise RemoteAttestationEvidenceV1Error("remote attestation lifetime exceeds trust-anchor lifetime")
    result=RemoteAttestationEvidenceV1(_text(v['provider_id'],"provider_id"),_text(v['trust_root_id'],"trust_root_id"),measure_raw_remote_attestation_v1(v['raw_evidence_bytes']),_text(v['environment_digest'],"environment_digest"),_text(v['workload_digest'],"workload_digest"),observed,expires,_text(v['verifier_abi_digest'],"verifier_abi_digest"),_text(v['verifier_implementation_digest'],"verifier_implementation_digest"),_text(v['trust_anchor_id'],"trust_anchor_id"),generation,_text(v['trust_anchor_manifest_digest'],"trust_anchor_manifest_digest"),anchor_start,anchor_end,_text(v['trust_anchor_admission_digest'],"trust_anchor_admission_digest"),"")
    object.__setattr__(result,"evidence_digest",hmac.new(key,_payload(provider_id=result.provider_id,trust_root_id=result.trust_root_id,raw_evidence_digest=result.raw_evidence_digest,environment_digest=result.environment_digest,workload_digest=result.workload_digest,observed_epoch=result.observed_epoch,expires_before_epoch=result.expires_before_epoch,verifier_abi_digest=result.attestation_verifier_abi_digest,verifier_implementation_digest=result.verifier_implementation_digest,trust_anchor_id=result.trust_anchor_id,trust_anchor_generation=result.trust_anchor_generation,trust_anchor_manifest_digest=result.trust_anchor_manifest_digest,trust_anchor_valid_from_epoch=result.trust_anchor_valid_from_epoch,trust_anchor_expires_before_epoch=result.trust_anchor_expires_before_epoch,trust_anchor_admission_digest=result.trust_anchor_runtime_admission_digest),hashlib.sha256).hexdigest())
    result.assert_authenticated(remote_attestation_verifier_key=key,raw_evidence_bytes=v['raw_evidence_bytes'],current_epoch=observed); return result
def verify_remote_attestation_with_abi_v1(*,abi:AttestationVerifierAbiV1,verifier_artifact_bytes:bytes,raw_evidence_bytes:bytes,current_epoch:int,verifier,remote_attestation_verifier_key:bytes,trust_anchor_manifest:TrustAnchorManifestV1,trust_anchor_admission:TrustAnchorRuntimeAdmissionV1,root_signing_key:bytes,trust_anchor_runtime_admission_key:bytes,trust_anchor_generation_state:TrustAnchorGenerationStateV1)->RemoteAttestationEvidenceV1:
    current=_epoch(current_epoch); abi.assert_sealed()
    trust_anchor_admission.assert_authenticated(runtime_admission_key=trust_anchor_runtime_admission_key,root_signing_key=root_signing_key,manifest=trust_anchor_manifest,abi=abi,verifier_artifact_bytes=verifier_artifact_bytes,current_epoch=current,generation_state=trust_anchor_generation_state)
    if measure_attestation_verifier_artifact_v1(verifier_artifact_bytes)!=abi.verifier_implementation_digest: raise RemoteAttestationEvidenceV1Error("attestation verifier artifact differs from ABI implementation digest")
    if not callable(verifier): raise RemoteAttestationEvidenceV1Error("attestation verifier must be callable")
    outcome=verifier(raw_evidence_bytes)
    if not isinstance(outcome,RemoteAttestationVerificationResultV1): raise RemoteAttestationEvidenceV1Error("attestation verifier returned invalid result type")
    trust_anchor_manifest.assert_trust_root_allowed(outcome.trust_root_id)
    observed=_epoch(outcome.observed_epoch); expires=_epoch(outcome.expires_before_epoch); anchor_start=_epoch(trust_anchor_manifest.valid_from_epoch); anchor_end=_epoch(trust_anchor_manifest.expires_before_epoch)
    if current<observed or current>=expires: raise RemoteAttestationEvidenceV1Error("attestation verifier result is not live at current epoch")
    if observed<anchor_start or observed>=anchor_end: raise RemoteAttestationEvidenceV1Error("attestation verifier result predates or exceeds trust-anchor lifetime")
    if expires>anchor_end: raise RemoteAttestationEvidenceV1Error("attestation verifier result lifetime exceeds trust-anchor manifest")
    result=_seal(provider_id=abi.provider_id,trust_root_id=outcome.trust_root_id,raw_evidence_bytes=raw_evidence_bytes,environment_digest=_measure_env(outcome.environment_bytes),workload_digest=_measure_workload(outcome.workload_bytes),observed_epoch=observed,expires_before_epoch=expires,verifier_abi_digest=abi.abi_digest,verifier_implementation_digest=abi.verifier_implementation_digest,trust_anchor_id=trust_anchor_manifest.anchor_id,trust_anchor_generation=trust_anchor_manifest.generation,trust_anchor_manifest_digest=trust_anchor_manifest.manifest_digest,trust_anchor_valid_from_epoch=anchor_start,trust_anchor_expires_before_epoch=anchor_end,trust_anchor_admission_digest=trust_anchor_admission.admission_digest,remote_attestation_verifier_key=remote_attestation_verifier_key)
    result.assert_current_generation(trust_anchor_generation_state=trust_anchor_generation_state)
    return result
