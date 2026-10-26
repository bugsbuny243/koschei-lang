"""Koschei Library activation freshness v0.

Adds time/epoch freshness, nonce anti-replay and explicit revocation on top of a
successful graph quorum decision. This layer is authority-free: it only derives
an activation eligibility receipt. Any stale, replayed, revoked or graph-mismatched
state fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .library_graph_quorum_v0 import GraphActivationDecisionV0

_CTX=b"koschei.library-activation-freshness/v0\x00"

class ActivationFreshnessError(ValueError): pass

@dataclass(frozen=True,slots=True)
class RevocationRecordV0:
    subject_id:str
    generation:int
    effective_epoch:int
    evidence_digest:bytes
    permanent:bool=True

@dataclass(frozen=True,slots=True)
class ActivationEpochStateV0:
    graph_digest:bytes
    current_epoch:int
    last_activation_epoch:int
    seen_nonce_digests:tuple[bytes,...]
    revocations:tuple[RevocationRecordV0,...]
    state_digest:bytes
    authority:bool=False

@dataclass(frozen=True,slots=True)
class FreshActivationReceiptV0:
    graph_digest:bytes
    decision_digest:bytes
    epoch:int
    nonce_digest:bytes
    receipt_digest:bytes
    eligible:bool
    authority:bool=False


def _d32(v:bytes,name:str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32:
        raise ActivationFreshnessError(f"{name} must be exactly 32 bytes")
    return v


def _state_digest(*,graph_digest:bytes,current_epoch:int,last_activation_epoch:int,seen_nonce_digests:tuple[bytes,...],revocations:tuple[RevocationRecordV0,...])->bytes:
    h=hashlib.sha3_256(_CTX+b"state\x00"+_d32(graph_digest,"graph_digest")+current_epoch.to_bytes(8,"big")+last_activation_epoch.to_bytes(8,"big"))
    for nonce in sorted(seen_nonce_digests): h.update(b"N\x00"+_d32(nonce,"nonce_digest"))
    for r in sorted(revocations,key=lambda x:(x.subject_id,x.generation,x.effective_epoch,x.evidence_digest)):
        h.update(b"R\x00"+r.subject_id.encode()+b"\x00"+r.generation.to_bytes(8,"big")+r.effective_epoch.to_bytes(8,"big")+_d32(r.evidence_digest,"evidence_digest")+(b"\x01" if r.permanent else b"\x00"))
    return h.digest()


def make_activation_epoch_state_v0(*,graph_digest:bytes,current_epoch:int,last_activation_epoch:int=0,seen_nonce_digests:tuple[bytes,...]=(),revocations:tuple[RevocationRecordV0,...]=())->ActivationEpochStateV0:
    _d32(graph_digest,"graph_digest")
    if not isinstance(current_epoch,int) or current_epoch<1: raise ActivationFreshnessError("current_epoch must be positive")
    if not isinstance(last_activation_epoch,int) or last_activation_epoch<0 or last_activation_epoch>current_epoch: raise ActivationFreshnessError("invalid last_activation_epoch")
    if not isinstance(seen_nonce_digests,tuple) or not isinstance(revocations,tuple): raise ActivationFreshnessError("state collections must be immutable tuples")
    if len(seen_nonce_digests)!=len(set(seen_nonce_digests)): raise ActivationFreshnessError("duplicate seen nonce forbidden")
    for n in seen_nonce_digests: _d32(n,"nonce_digest")
    keys=set()
    for r in revocations:
        if not isinstance(r,RevocationRecordV0) or not r.subject_id or r.generation<1 or r.effective_epoch<1: raise ActivationFreshnessError("invalid revocation record")
        _d32(r.evidence_digest,"evidence_digest")
        k=(r.subject_id,r.generation,r.effective_epoch,r.evidence_digest)
        if k in keys: raise ActivationFreshnessError("duplicate revocation record forbidden")
        keys.add(k)
    digest=_state_digest(graph_digest=graph_digest,current_epoch=current_epoch,last_activation_epoch=last_activation_epoch,seen_nonce_digests=seen_nonce_digests,revocations=revocations)
    return ActivationEpochStateV0(graph_digest,current_epoch,last_activation_epoch,seen_nonce_digests,revocations,digest,False)


def advance_activation_epoch_v0(state:ActivationEpochStateV0,*,new_epoch:int)->ActivationEpochStateV0:
    if not isinstance(state,ActivationEpochStateV0) or state.authority: raise ActivationFreshnessError("authority-free epoch state required")
    if not isinstance(new_epoch,int) or new_epoch<=state.current_epoch: raise ActivationFreshnessError("epoch must advance monotonically")
    return make_activation_epoch_state_v0(graph_digest=state.graph_digest,current_epoch=new_epoch,last_activation_epoch=state.last_activation_epoch,seen_nonce_digests=state.seen_nonce_digests,revocations=state.revocations)


def add_revocation_v0(state:ActivationEpochStateV0,revocation:RevocationRecordV0)->ActivationEpochStateV0:
    if not isinstance(state,ActivationEpochStateV0) or state.authority: raise ActivationFreshnessError("authority-free epoch state required")
    if not isinstance(revocation,RevocationRecordV0): raise ActivationFreshnessError("revocation record required")
    return make_activation_epoch_state_v0(graph_digest=state.graph_digest,current_epoch=state.current_epoch,last_activation_epoch=state.last_activation_epoch,seen_nonce_digests=state.seen_nonce_digests,revocations=state.revocations+(revocation,))


def evaluate_fresh_activation_v0(*,decision:GraphActivationDecisionV0,state:ActivationEpochStateV0,nonce_digest:bytes,subject_generations:tuple[tuple[str,int],...],max_epoch_lag:int=0)->tuple[FreshActivationReceiptV0,ActivationEpochStateV0]:
    if not isinstance(decision,GraphActivationDecisionV0) or decision.authority: raise ActivationFreshnessError("authority-free graph decision required")
    if not isinstance(state,ActivationEpochStateV0) or state.authority: raise ActivationFreshnessError("authority-free epoch state required")
    if decision.graph_digest!=state.graph_digest: raise ActivationFreshnessError("decision/state graph mismatch")
    if not decision.active: raise ActivationFreshnessError("inactive quorum decision cannot activate")
    nonce=_d32(nonce_digest,"nonce_digest")
    if nonce in state.seen_nonce_digests: raise ActivationFreshnessError("activation nonce replay detected")
    if not isinstance(subject_generations,tuple) or not subject_generations: raise ActivationFreshnessError("subject generations required")
    if len(subject_generations)!=len({x[0] for x in subject_generations}): raise ActivationFreshnessError("duplicate subject generation forbidden")
    if not isinstance(max_epoch_lag,int) or max_epoch_lag<0: raise ActivationFreshnessError("invalid max_epoch_lag")
    if state.last_activation_epoch and state.current_epoch+max_epoch_lag<state.last_activation_epoch: raise ActivationFreshnessError("activation epoch regressed")
    for subject_id,generation in subject_generations:
        if not subject_id or not isinstance(generation,int) or generation<1: raise ActivationFreshnessError("invalid subject generation")
        for r in state.revocations:
            if r.subject_id==subject_id and r.generation==generation and r.effective_epoch<=state.current_epoch:
                raise ActivationFreshnessError("revoked subject generation cannot activate")
    h=hashlib.sha3_256(_CTX+b"receipt\x00"+state.graph_digest+decision.decision_digest+state.current_epoch.to_bytes(8,"big")+nonce+state.state_digest)
    for subject_id,generation in sorted(subject_generations): h.update(subject_id.encode()+b"\x00"+generation.to_bytes(8,"big"))
    receipt=FreshActivationReceiptV0(state.graph_digest,decision.decision_digest,state.current_epoch,nonce,h.digest(),True,False)
    next_state=make_activation_epoch_state_v0(graph_digest=state.graph_digest,current_epoch=state.current_epoch,last_activation_epoch=state.current_epoch,seen_nonce_digests=state.seen_nonce_digests+(nonce,),revocations=state.revocations)
    return receipt,next_state
