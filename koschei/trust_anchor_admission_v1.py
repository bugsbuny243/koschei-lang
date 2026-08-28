"""Non-recursive trust-anchor admission for attestation verifiers in Koschei Lang v1.

V1 also carries a process-local monotonic manifest-generation state. It prevents an
already-observed newer manifest from being replaced by an older generation inside the
same state instance. Durable/fork-safe monotonic storage is intentionally out of scope.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,hmac
from .attestation_verifier_abi_v1 import AttestationVerifierAbiV1,measure_attestation_verifier_artifact_v1

_MANIFEST_CTX=b"koschei.trust-anchor-manifest/v1\x00"
_ADMISSION_CTX=b"koschei.trust-anchor-runtime-admission/v1\x00"

class TrustAnchorAdmissionV1Error(ValueError): pass

def _key(v:bytes,label:str)->bytes:
    if not isinstance(v,bytes) or len(v)<32: raise TrustAnchorAdmissionV1Error(f"{label} must contain at least 32 bytes")
    return v

def _text(v:str,label:str)->str:
    if not isinstance(v,str) or not v.strip(): raise TrustAnchorAdmissionV1Error(f"{label} cannot be empty")
    return v.strip()
def _epoch(v:int)->int:
    if not isinstance(v,int) or isinstance(v,bool) or v<0: raise TrustAnchorAdmissionV1Error("epoch must be a non-negative integer")
    return v
def _generation(v:int)->int:
    if not isinstance(v,int) or isinstance(v,bool) or v<0: raise TrustAnchorAdmissionV1Error("generation must be a non-negative integer")
    return v
def _norm(values,label):
    if not isinstance(values,(tuple,list,set)): raise TrustAnchorAdmissionV1Error(f"{label} must be a collection")
    return tuple(sorted({_text(v,label) for v in values}))

def _manifest_payload(**v)->bytes:
    rows=(f"anchor={v['anchor_id']}",f"generation={v['generation']}",f"abi={v['abi_digest']}",f"implementation={v['implementation_digest']}",f"allowed_roots={','.join(v['allowed_roots'])}",f"revoked_roots={','.join(v['revoked_roots'])}",f"valid_from={v['valid_from']}",f"expires_before={v['expires_before']}",f"revoked_verifier={1 if v['revoked_verifier'] else 0}","authority=0")
    return _MANIFEST_CTX+"\n".join(rows).encode()

@dataclass(frozen=True,slots=True)
class TrustAnchorManifestV1:
    anchor_id:str; generation:int; attestation_verifier_abi_digest:str; verifier_implementation_digest:str; allowed_trust_root_ids:tuple[str,...]; revoked_trust_root_ids:tuple[str,...]; valid_from_epoch:int; expires_before_epoch:int; revoked_verifier:bool; manifest_digest:str; authority:bool=False; version:int=1
    def assert_authenticated(self,*,root_signing_key:bytes,abi:AttestationVerifierAbiV1,current_epoch:int)->None:
        key=_key(root_signing_key,"root_signing_key"); abi.assert_sealed(); current=_epoch(current_epoch); generation=_generation(self.generation)
        if self.authority: raise TrustAnchorAdmissionV1Error("trust-anchor manifest cannot carry ambient authority")
        if self.attestation_verifier_abi_digest!=abi.abi_digest or self.verifier_implementation_digest!=abi.verifier_implementation_digest: raise TrustAnchorAdmissionV1Error("trust-anchor verifier binding mismatch")
        start=_epoch(self.valid_from_epoch); end=_epoch(self.expires_before_epoch)
        if end<=start: raise TrustAnchorAdmissionV1Error("trust-anchor expiry must be after valid-from epoch")
        if current<start or current>=end: raise TrustAnchorAdmissionV1Error("trust-anchor manifest is not live")
        if self.revoked_verifier: raise TrustAnchorAdmissionV1Error("attestation verifier is revoked")
        allowed=_norm(self.allowed_trust_root_ids,"allowed_trust_root_ids"); revoked=_norm(self.revoked_trust_root_ids,"revoked_trust_root_ids")
        if not allowed: raise TrustAnchorAdmissionV1Error("at least one trust root must be allowed")
        if set(allowed)&set(revoked): raise TrustAnchorAdmissionV1Error("trust root cannot be both allowed and revoked")
        expected=hmac.new(key,_manifest_payload(anchor_id=_text(self.anchor_id,"anchor_id"),generation=generation,abi_digest=self.attestation_verifier_abi_digest,implementation_digest=self.verifier_implementation_digest,allowed_roots=allowed,revoked_roots=revoked,valid_from=start,expires_before=end,revoked_verifier=self.revoked_verifier),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.manifest_digest,expected): raise TrustAnchorAdmissionV1Error("trust-anchor manifest authentication failed")
    def assert_trust_root_allowed(self,trust_root_id:str)->None:
        root=_text(trust_root_id,"trust_root_id")
        if root in self.revoked_trust_root_ids: raise TrustAnchorAdmissionV1Error("attestation trust root is revoked")
        if root not in self.allowed_trust_root_ids: raise TrustAnchorAdmissionV1Error("attestation trust root is not allowed")

class TrustAnchorGenerationStateV1:
    """Process-local anti-rollback state keyed by anchor id.

    Production must replace/persist this state in rollback-resistant monotonic storage.
    """
    def __init__(self)->None:
        self._highest:dict[str,tuple[int,str]]={}
    def observe(self,manifest:TrustAnchorManifestV1,*,root_signing_key:bytes,abi:AttestationVerifierAbiV1,current_epoch:int)->None:
        manifest.assert_authenticated(root_signing_key=root_signing_key,abi=abi,current_epoch=current_epoch)
        anchor=_text(manifest.anchor_id,"anchor_id"); generation=_generation(manifest.generation); prior=self._highest.get(anchor)
        if prior is not None:
            prior_generation,prior_digest=prior
            if generation<prior_generation: raise TrustAnchorAdmissionV1Error("trust-anchor manifest generation rollback detected")
            if generation==prior_generation and manifest.manifest_digest!=prior_digest: raise TrustAnchorAdmissionV1Error("trust-anchor manifest generation equivocation detected")
        if prior is None or generation>prior[0]: self._highest[anchor]=(generation,manifest.manifest_digest)
    def assert_current(self,manifest:TrustAnchorManifestV1)->None:
        anchor=_text(manifest.anchor_id,"anchor_id"); generation=_generation(manifest.generation); prior=self._highest.get(anchor)
        if prior is None: raise TrustAnchorAdmissionV1Error("trust-anchor generation state has not observed this anchor")
        if generation!=prior[0] or manifest.manifest_digest!=prior[1]: raise TrustAnchorAdmissionV1Error("trust-anchor manifest is not the current observed generation")
    def highest_generation(self,anchor_id:str)->int|None:
        prior=self._highest.get(_text(anchor_id,"anchor_id")); return None if prior is None else prior[0]

def seal_trust_anchor_manifest_v1(*,anchor_id:str,generation:int,abi:AttestationVerifierAbiV1,allowed_trust_root_ids,revoked_trust_root_ids=(),valid_from_epoch:int,expires_before_epoch:int,revoked_verifier:bool=False,root_signing_key:bytes)->TrustAnchorManifestV1:
    abi.assert_sealed(); key=_key(root_signing_key,"root_signing_key"); allowed=_norm(allowed_trust_root_ids,"allowed_trust_root_ids"); revoked=_norm(revoked_trust_root_ids,"revoked_trust_root_ids"); start=_epoch(valid_from_epoch); end=_epoch(expires_before_epoch); gen=_generation(generation)
    if end<=start: raise TrustAnchorAdmissionV1Error("trust-anchor expiry must be after valid-from epoch")
    if not allowed: raise TrustAnchorAdmissionV1Error("at least one trust root must be allowed")
    if set(allowed)&set(revoked): raise TrustAnchorAdmissionV1Error("trust root cannot be both allowed and revoked")
    result=TrustAnchorManifestV1(_text(anchor_id,"anchor_id"),gen,abi.abi_digest,abi.verifier_implementation_digest,allowed,revoked,start,end,bool(revoked_verifier),"")
    object.__setattr__(result,"manifest_digest",hmac.new(key,_manifest_payload(anchor_id=result.anchor_id,generation=result.generation,abi_digest=result.attestation_verifier_abi_digest,implementation_digest=result.verifier_implementation_digest,allowed_roots=result.allowed_trust_root_ids,revoked_roots=result.revoked_trust_root_ids,valid_from=result.valid_from_epoch,expires_before=result.expires_before_epoch,revoked_verifier=result.revoked_verifier),hashlib.sha256).hexdigest())
    result.assert_authenticated(root_signing_key=key,abi=abi,current_epoch=start)
    return result

def _admission_payload(manifest_digest,generation,abi_digest,implementation_digest,epoch):
    return _ADMISSION_CTX+f"manifest={manifest_digest}\ngeneration={generation}\nabi={abi_digest}\nimplementation={implementation_digest}\nepoch={epoch}\nadmitted=1\nauthority=0".encode()
@dataclass(frozen=True,slots=True)
class TrustAnchorRuntimeAdmissionV1:
    manifest_digest:str; manifest_generation:int; attestation_verifier_abi_digest:str; verifier_implementation_digest:str; admitted_epoch:int; admission_digest:str; admitted:bool=True; authority:bool=False; version:int=1
    def assert_authenticated(self,*,runtime_admission_key:bytes,root_signing_key:bytes,manifest:TrustAnchorManifestV1,abi:AttestationVerifierAbiV1,verifier_artifact_bytes:bytes,current_epoch:int,generation_state:TrustAnchorGenerationStateV1)->None:
        key=_key(runtime_admission_key,"runtime_admission_key"); current=_epoch(current_epoch); manifest.assert_authenticated(root_signing_key=root_signing_key,abi=abi,current_epoch=current); generation_state.assert_current(manifest)
        if self.authority or self.admitted is not True: raise TrustAnchorAdmissionV1Error("trust-anchor runtime admission must remain non-authoritative and admitted")
        measured=measure_attestation_verifier_artifact_v1(verifier_artifact_bytes)
        if measured!=abi.verifier_implementation_digest: raise TrustAnchorAdmissionV1Error("attestation verifier artifact does not match ABI")
        if self.manifest_digest!=manifest.manifest_digest or self.manifest_generation!=manifest.generation or self.attestation_verifier_abi_digest!=abi.abi_digest or self.verifier_implementation_digest!=measured or self.admitted_epoch!=current: raise TrustAnchorAdmissionV1Error("trust-anchor runtime admission binding mismatch")
        expected=hmac.new(key,_admission_payload(self.manifest_digest,self.manifest_generation,self.attestation_verifier_abi_digest,self.verifier_implementation_digest,self.admitted_epoch),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.admission_digest,expected): raise TrustAnchorAdmissionV1Error("trust-anchor runtime admission authentication failed")
def admit_attestation_verifier_from_trust_anchor_v1(*,manifest:TrustAnchorManifestV1,abi:AttestationVerifierAbiV1,verifier_artifact_bytes:bytes,current_epoch:int,root_signing_key:bytes,runtime_admission_key:bytes,generation_state:TrustAnchorGenerationStateV1)->TrustAnchorRuntimeAdmissionV1:
    current=_epoch(current_epoch); generation_state.observe(manifest,root_signing_key=root_signing_key,abi=abi,current_epoch=current); measured=measure_attestation_verifier_artifact_v1(verifier_artifact_bytes)
    if measured!=abi.verifier_implementation_digest: raise TrustAnchorAdmissionV1Error("attestation verifier artifact does not match ABI")
    result=TrustAnchorRuntimeAdmissionV1(manifest.manifest_digest,manifest.generation,abi.abi_digest,measured,current,"")
    key=_key(runtime_admission_key,"runtime_admission_key"); object.__setattr__(result,"admission_digest",hmac.new(key,_admission_payload(result.manifest_digest,result.manifest_generation,result.attestation_verifier_abi_digest,result.verifier_implementation_digest,result.admitted_epoch),hashlib.sha256).hexdigest())
    result.assert_authenticated(runtime_admission_key=key,root_signing_key=root_signing_key,manifest=manifest,abi=abi,verifier_artifact_bytes=verifier_artifact_bytes,current_epoch=current,generation_state=generation_state)
    return result
