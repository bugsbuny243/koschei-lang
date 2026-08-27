"""Provider-neutral attestation-verifier ABI identity for Koschei Lang v1."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib

_CTX=b"koschei.attestation-verifier-abi/v1\x00"
_ARTIFACT_CTX=b"koschei.attestation-verifier-artifact/v1\x00"

class AttestationVerifierAbiV1Error(ValueError): pass

def _text(v:str,label:str)->str:
    if not isinstance(v,str) or not v.strip(): raise AttestationVerifierAbiV1Error(f"{label} cannot be empty")
    return v.strip()

def measure_attestation_verifier_artifact_v1(artifact_bytes:bytes)->str:
    if not isinstance(artifact_bytes,bytes) or not artifact_bytes: raise AttestationVerifierAbiV1Error("artifact_bytes must be non-empty bytes")
    return hashlib.sha256(_ARTIFACT_CTX+artifact_bytes).hexdigest()
def _digest(provider_id,evidence_format_id,schema_version,implementation_digest):
    rows=(f"provider={provider_id}",f"format={evidence_format_id}",f"schema={schema_version}",f"implementation={implementation_digest}","authority=0")
    return hashlib.sha256(_CTX+"\n".join(rows).encode()).hexdigest()
@dataclass(frozen=True,slots=True)
class AttestationVerifierAbiV1:
    provider_id:str; evidence_format_id:str; schema_version:str; verifier_implementation_digest:str; abi_digest:str; authority:bool=False; version:int=1
    def assert_sealed(self)->None:
        if self.authority: raise AttestationVerifierAbiV1Error("attestation verifier ABI cannot carry ambient authority")
        p=_text(self.provider_id,"provider_id"); f=_text(self.evidence_format_id,"evidence_format_id"); s=_text(self.schema_version,"schema_version")
        if not isinstance(self.verifier_implementation_digest,str) or len(self.verifier_implementation_digest)!=64: raise AttestationVerifierAbiV1Error("verifier implementation digest must be 64 characters")
        if self.abi_digest!=_digest(p,f,s,self.verifier_implementation_digest): raise AttestationVerifierAbiV1Error("attestation verifier ABI seal mismatch")
def seal_attestation_verifier_abi_v1(*,provider_id:str,evidence_format_id:str,schema_version:str,verifier_artifact_bytes:bytes)->AttestationVerifierAbiV1:
    p=_text(provider_id,"provider_id"); f=_text(evidence_format_id,"evidence_format_id"); s=_text(schema_version,"schema_version"); impl=measure_attestation_verifier_artifact_v1(verifier_artifact_bytes)
    result=AttestationVerifierAbiV1(p,f,s,impl,_digest(p,f,s,impl)); result.assert_sealed(); return result
