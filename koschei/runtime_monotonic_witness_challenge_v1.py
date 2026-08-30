"""Runtime-owned fresh challenge receipts for monotonic witness verification v1.

Production witness freshness must not depend on application-selected nonce bytes. The
sanctioned issuer generates challenge material with `secrets.token_bytes` and authenticates
its anchor/epoch/lifetime under a dedicated runtime challenge key.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,hmac,secrets

_CTX=b"koschei.runtime-monotonic-witness-challenge/v1\x00"
_BYTES_CTX=b"koschei.runtime-monotonic-witness-challenge-bytes/v1\x00"

class RuntimeMonotonicWitnessChallengeV1Error(ValueError): pass

def _text(v:str,label:str)->str:
    if not isinstance(v,str) or not v.strip(): raise RuntimeMonotonicWitnessChallengeV1Error(f"{label} cannot be empty")
    return v.strip()
def _key(v:bytes)->bytes:
    if not isinstance(v,bytes) or len(v)<32: raise RuntimeMonotonicWitnessChallengeV1Error("witness_challenge_key must contain at least 32 bytes")
    return v
def _epoch(v:int,label:str)->int:
    if not isinstance(v,int) or isinstance(v,bool) or v<0: raise RuntimeMonotonicWitnessChallengeV1Error(f"{label} must be a non-negative integer")
    return v
def _challenge_digest(v:bytes)->str:
    if not isinstance(v,bytes) or len(v)<32: raise RuntimeMonotonicWitnessChallengeV1Error("runtime witness challenge must contain at least 32 bytes")
    return hashlib.sha256(_BYTES_CTX+v).hexdigest()
def _payload(*,anchor_id:str,challenge_digest:str,issued_epoch:int,expires_before_epoch:int)->bytes:
    return _CTX+"\n".join((f"anchor={anchor_id}",f"challenge={challenge_digest}",f"issued={issued_epoch}",f"expires_before={expires_before_epoch}","authority=0")).encode()

@dataclass(frozen=True,slots=True)
class RuntimeMonotonicWitnessChallengeV1:
    anchor_id:str; challenge_bytes:bytes; challenge_digest:str; issued_epoch:int; expires_before_epoch:int; receipt_digest:str; authority:bool=False; version:int=1
    def assert_authenticated(self,*,witness_challenge_key:bytes)->None:
        key=_key(witness_challenge_key); anchor=_text(self.anchor_id,"anchor_id"); issued=_epoch(self.issued_epoch,"issued_epoch"); expires=_epoch(self.expires_before_epoch,"expires_before_epoch")
        if self.authority: raise RuntimeMonotonicWitnessChallengeV1Error("runtime witness challenge cannot carry ambient authority")
        if expires<=issued: raise RuntimeMonotonicWitnessChallengeV1Error("runtime witness challenge expiry must be after issuance")
        digest=_challenge_digest(self.challenge_bytes)
        if self.challenge_digest!=digest: raise RuntimeMonotonicWitnessChallengeV1Error("runtime witness challenge bytes do not match challenge digest")
        expected=hmac.new(key,_payload(anchor_id=anchor,challenge_digest=digest,issued_epoch=issued,expires_before_epoch=expires),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.receipt_digest,expected): raise RuntimeMonotonicWitnessChallengeV1Error("runtime witness challenge authentication failed")
    def assert_live(self,*,witness_challenge_key:bytes,current_epoch:int,expected_anchor_id:str)->None:
        self.assert_authenticated(witness_challenge_key=witness_challenge_key); current=_epoch(current_epoch,"current_epoch")
        if self.anchor_id!=_text(expected_anchor_id,"expected_anchor_id"): raise RuntimeMonotonicWitnessChallengeV1Error("runtime witness challenge anchor mismatch")
        if current<self.issued_epoch or current>=self.expires_before_epoch: raise RuntimeMonotonicWitnessChallengeV1Error("runtime witness challenge is not live")

def issue_runtime_monotonic_witness_challenge_v1(*,anchor_id:str,current_epoch:int,ttl_epochs:int,witness_challenge_key:bytes)->RuntimeMonotonicWitnessChallengeV1:
    anchor=_text(anchor_id,"anchor_id"); issued=_epoch(current_epoch,"current_epoch"); ttl=_epoch(ttl_epochs,"ttl_epochs")
    if ttl<1: raise RuntimeMonotonicWitnessChallengeV1Error("ttl_epochs must be at least 1")
    expires=issued+ttl; challenge=secrets.token_bytes(32); digest=_challenge_digest(challenge); key=_key(witness_challenge_key)
    receipt=RuntimeMonotonicWitnessChallengeV1(anchor,challenge,digest,issued,expires,"")
    object.__setattr__(receipt,"receipt_digest",hmac.new(key,_payload(anchor_id=anchor,challenge_digest=digest,issued_epoch=issued,expires_before_epoch=expires),hashlib.sha256).hexdigest())
    receipt.assert_live(witness_challenge_key=key,current_epoch=issued,expected_anchor_id=anchor); return receipt
