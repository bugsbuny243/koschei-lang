"""Provider-neutral external monotonic witness boundary for Koschei Lang v1.

A local generation store cannot detect restoration of a complete older, internally valid
snapshot. This module lets a runtime compare that local binding with a fresh external
witness result without teaching Lang core any TPM/cloud/transparency-log protocol.

The provider-specific verifier remains a trusted callback. V1 binds its exact artifact
identity, the exact raw witness response, a runtime challenge, and the canonical witness
result into a non-authoritative authenticated receipt.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,hmac
from typing import Callable,Protocol

_ABI_CTX=b"koschei.monotonic-witness-abi/v1\x00"
_ARTIFACT_CTX=b"koschei.monotonic-witness-verifier-artifact/v1\x00"
_RAW_CTX=b"koschei.monotonic-witness-raw-response/v1\x00"
_CHALLENGE_CTX=b"koschei.monotonic-witness-challenge/v1\x00"
_PROOF_CTX=b"koschei.monotonic-witness-provider-proof/v1\x00"
_RECEIPT_CTX=b"koschei.monotonic-witness-receipt/v1\x00"

class MonotonicWitnessV1Error(ValueError): pass

def _text(v:str,label:str)->str:
    if not isinstance(v,str) or not v.strip(): raise MonotonicWitnessV1Error(f"{label} cannot be empty")
    return v.strip()
def _key(v:bytes,label:str)->bytes:
    if not isinstance(v,bytes) or len(v)<32: raise MonotonicWitnessV1Error(f"{label} must contain at least 32 bytes")
    return v
def _bytes(v:bytes,label:str)->bytes:
    if not isinstance(v,bytes) or not v: raise MonotonicWitnessV1Error(f"{label} must be non-empty bytes")
    return v
def _int(v:int,label:str)->int:
    if not isinstance(v,int) or isinstance(v,bool) or v<0: raise MonotonicWitnessV1Error(f"{label} must be a non-negative integer")
    return v
def _hash(ctx:bytes,v:bytes,label:str)->str: return hashlib.sha256(ctx+_bytes(v,label)).hexdigest()

def measure_monotonic_witness_verifier_artifact_v1(verifier_artifact_bytes:bytes)->str:
    return _hash(_ARTIFACT_CTX,verifier_artifact_bytes,"verifier_artifact_bytes")

def _abi_payload(*,provider_id:str,protocol_id:str,schema_version:str,implementation_digest:str)->bytes:
    return _ABI_CTX+"\n".join((f"provider={provider_id}",f"protocol={protocol_id}",f"schema={schema_version}",f"implementation={implementation_digest}","authority=0")).encode()

@dataclass(frozen=True,slots=True)
class MonotonicWitnessAbiV1:
    provider_id:str; protocol_id:str; schema_version:str; verifier_implementation_digest:str; abi_digest:str; authority:bool=False; version:int=1
    def assert_sealed(self)->None:
        if self.authority: raise MonotonicWitnessV1Error("monotonic witness ABI cannot carry ambient authority")
        provider=_text(self.provider_id,"provider_id"); protocol=_text(self.protocol_id,"protocol_id"); schema=_text(self.schema_version,"schema_version"); implementation=_text(self.verifier_implementation_digest,"verifier_implementation_digest")
        expected=hashlib.sha256(_abi_payload(provider_id=provider,protocol_id=protocol,schema_version=schema,implementation_digest=implementation)).hexdigest()
        if self.abi_digest!=expected: raise MonotonicWitnessV1Error("monotonic witness ABI seal mismatch")

def seal_monotonic_witness_abi_v1(*,provider_id:str,protocol_id:str,schema_version:str,verifier_artifact_bytes:bytes)->MonotonicWitnessAbiV1:
    provider=_text(provider_id,"provider_id"); protocol=_text(protocol_id,"protocol_id"); schema=_text(schema_version,"schema_version"); implementation=measure_monotonic_witness_verifier_artifact_v1(verifier_artifact_bytes)
    digest=hashlib.sha256(_abi_payload(provider_id=provider,protocol_id=protocol,schema_version=schema,implementation_digest=implementation)).hexdigest()
    result=MonotonicWitnessAbiV1(provider,protocol,schema,implementation,digest)
    result.assert_sealed(); return result

@dataclass(frozen=True,slots=True)
class MonotonicWitnessVerificationResultV1:
    anchor_id:str; generation:int; manifest_digest:str; witness_counter:int; observed_epoch:int; expires_before_epoch:int; challenge_bytes:bytes; proof_bytes:bytes

def _receipt_payload(**v)->bytes:
    rows=(f"provider={v['provider_id']}",f"abi={v['abi_digest']}",f"implementation={v['implementation_digest']}",f"anchor={v['anchor_id']}",f"generation={v['generation']}",f"manifest={v['manifest_digest']}",f"counter={v['counter']}",f"observed={v['observed']}",f"expires_before={v['expires_before']}",f"challenge={v['challenge_digest']}",f"raw_response={v['raw_response_digest']}",f"provider_proof={v['provider_proof_digest']}","authority=0")
    return _RECEIPT_CTX+"\n".join(rows).encode()

@dataclass(frozen=True,slots=True)
class MonotonicWitnessReceiptV1:
    provider_id:str; witness_abi_digest:str; verifier_implementation_digest:str; anchor_id:str; generation:int; manifest_digest:str; witness_counter:int; observed_epoch:int; expires_before_epoch:int; challenge_digest:str; raw_response_digest:str; provider_proof_digest:str; receipt_digest:str; authority:bool=False; version:int=1
    def assert_integrity(self,*,abi:MonotonicWitnessAbiV1,verifier_artifact_bytes:bytes,raw_response_bytes:bytes,challenge_bytes:bytes,witness_verifier_key:bytes)->None:
        key=_key(witness_verifier_key,"witness_verifier_key"); abi.assert_sealed()
        measured=measure_monotonic_witness_verifier_artifact_v1(verifier_artifact_bytes)
        if measured!=abi.verifier_implementation_digest: raise MonotonicWitnessV1Error("monotonic witness verifier artifact differs from ABI")
        if self.authority: raise MonotonicWitnessV1Error("monotonic witness receipt cannot carry ambient authority")
        generation=_int(self.generation,"generation"); counter=_int(self.witness_counter,"witness_counter"); observed=_int(self.observed_epoch,"observed_epoch"); expires=_int(self.expires_before_epoch,"expires_before_epoch")
        if expires<=observed: raise MonotonicWitnessV1Error("monotonic witness expiry must be after observation")
        expected_links=((self.provider_id,abi.provider_id,"provider"),(self.witness_abi_digest,abi.abi_digest,"ABI"),(self.verifier_implementation_digest,measured,"verifier implementation"),(self.challenge_digest,_hash(_CHALLENGE_CTX,challenge_bytes,"challenge_bytes"),"challenge"),(self.raw_response_digest,_hash(_RAW_CTX,raw_response_bytes,"raw_response_bytes"),"raw response"))
        for actual,expected,label in expected_links:
            if actual!=expected: raise MonotonicWitnessV1Error(f"monotonic witness receipt {label} mismatch")
        expected=hmac.new(key,_receipt_payload(provider_id=_text(self.provider_id,"provider_id"),abi_digest=self.witness_abi_digest,implementation_digest=self.verifier_implementation_digest,anchor_id=_text(self.anchor_id,"anchor_id"),generation=generation,manifest_digest=_text(self.manifest_digest,"manifest_digest"),counter=counter,observed=observed,expires_before=expires,challenge_digest=self.challenge_digest,raw_response_digest=self.raw_response_digest,provider_proof_digest=_text(self.provider_proof_digest,"provider_proof_digest")),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.receipt_digest,expected): raise MonotonicWitnessV1Error("monotonic witness receipt authentication failed")
    def assert_live(self,*,abi:MonotonicWitnessAbiV1,verifier_artifact_bytes:bytes,raw_response_bytes:bytes,challenge_bytes:bytes,witness_verifier_key:bytes,current_epoch:int)->None:
        self.assert_integrity(abi=abi,verifier_artifact_bytes=verifier_artifact_bytes,raw_response_bytes=raw_response_bytes,challenge_bytes=challenge_bytes,witness_verifier_key=witness_verifier_key)
        current=_int(current_epoch,"current_epoch")
        if current<self.observed_epoch or current>=self.expires_before_epoch: raise MonotonicWitnessV1Error("monotonic witness receipt is not live")

def verify_monotonic_witness_response_v1(*,abi:MonotonicWitnessAbiV1,verifier_artifact_bytes:bytes,raw_response_bytes:bytes,expected_anchor_id:str,challenge_bytes:bytes,current_epoch:int,verifier:Callable[[bytes,bytes],MonotonicWitnessVerificationResultV1],witness_verifier_key:bytes)->MonotonicWitnessReceiptV1:
    abi.assert_sealed(); key=_key(witness_verifier_key,"witness_verifier_key"); measured=measure_monotonic_witness_verifier_artifact_v1(verifier_artifact_bytes)
    if measured!=abi.verifier_implementation_digest: raise MonotonicWitnessV1Error("monotonic witness verifier artifact differs from ABI")
    anchor=_text(expected_anchor_id,"expected_anchor_id"); challenge=_bytes(challenge_bytes,"challenge_bytes"); current=_int(current_epoch,"current_epoch")
    if not callable(verifier): raise MonotonicWitnessV1Error("monotonic witness verifier must be callable")
    raw_digest=_hash(_RAW_CTX,raw_response_bytes,"raw_response_bytes"); challenge_digest=_hash(_CHALLENGE_CTX,challenge,"challenge_bytes")
    result=verifier(raw_response_bytes,challenge)
    if not isinstance(result,MonotonicWitnessVerificationResultV1): raise MonotonicWitnessV1Error("monotonic witness verifier returned invalid result type")
    if _text(result.anchor_id,"anchor_id")!=anchor: raise MonotonicWitnessV1Error("monotonic witness result anchor differs from expected anchor")
    generation=_int(result.generation,"generation"); manifest=_text(result.manifest_digest,"manifest_digest"); counter=_int(result.witness_counter,"witness_counter"); observed=_int(result.observed_epoch,"observed_epoch"); expires=_int(result.expires_before_epoch,"expires_before_epoch")
    if result.challenge_bytes!=challenge: raise MonotonicWitnessV1Error("monotonic witness result challenge mismatch")
    if expires<=observed or current<observed or current>=expires: raise MonotonicWitnessV1Error("monotonic witness result is not live")
    proof_digest=_hash(_PROOF_CTX,result.proof_bytes,"proof_bytes")
    receipt=MonotonicWitnessReceiptV1(abi.provider_id,abi.abi_digest,measured,anchor,generation,manifest,counter,observed,expires,challenge_digest,raw_digest,proof_digest,"")
    object.__setattr__(receipt,"receipt_digest",hmac.new(key,_receipt_payload(provider_id=receipt.provider_id,abi_digest=receipt.witness_abi_digest,implementation_digest=receipt.verifier_implementation_digest,anchor_id=receipt.anchor_id,generation=receipt.generation,manifest_digest=receipt.manifest_digest,counter=receipt.witness_counter,observed=receipt.observed_epoch,expires_before=receipt.expires_before_epoch,challenge_digest=receipt.challenge_digest,raw_response_digest=receipt.raw_response_digest,provider_proof_digest=receipt.provider_proof_digest),hashlib.sha256).hexdigest())
    receipt.assert_live(abi=abi,verifier_artifact_bytes=verifier_artifact_bytes,raw_response_bytes=raw_response_bytes,challenge_bytes=challenge,witness_verifier_key=key,current_epoch=current)
    return receipt

class GenerationStateLikeV1(Protocol):
    def assert_current_binding(self,*,anchor_id:str,generation:int,manifest_digest:str)->None: ...
    def highest_generation(self,anchor_id:str)->int|None: ...

class WitnessConfirmedGenerationStateV1:
    """Read-side generation guard requiring local state and a live external witness to agree exactly."""
    def __init__(self,*,local_state:GenerationStateLikeV1,witness_receipt:MonotonicWitnessReceiptV1,abi:MonotonicWitnessAbiV1,verifier_artifact_bytes:bytes,raw_response_bytes:bytes,challenge_bytes:bytes,witness_verifier_key:bytes,current_epoch:int)->None:
        self._local=local_state; self._receipt=witness_receipt; self._abi=abi; self._artifact=verifier_artifact_bytes; self._raw=raw_response_bytes; self._challenge=challenge_bytes; self._key=witness_verifier_key; self._current=current_epoch
    @property
    def witness_receipt_digest(self)->str: return self._receipt.receipt_digest
    def _assert_witness(self)->None:
        self._receipt.assert_live(abi=self._abi,verifier_artifact_bytes=self._artifact,raw_response_bytes=self._raw,challenge_bytes=self._challenge,witness_verifier_key=self._key,current_epoch=self._current)
    def assert_current_binding(self,*,anchor_id:str,generation:int,manifest_digest:str)->None:
        self._local.assert_current_binding(anchor_id=anchor_id,generation=generation,manifest_digest=manifest_digest); self._assert_witness()
        if self._receipt.anchor_id!=anchor_id or self._receipt.generation!=generation or self._receipt.manifest_digest!=manifest_digest: raise MonotonicWitnessV1Error("local generation binding differs from external monotonic witness")
    def highest_generation(self,anchor_id:str)->int|None:
        self._assert_witness(); local=self._local.highest_generation(anchor_id)
        if self._receipt.anchor_id!=anchor_id: return local
        if local!=self._receipt.generation: raise MonotonicWitnessV1Error("local highest generation differs from external monotonic witness")
        return local
