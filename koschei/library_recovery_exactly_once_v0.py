"""Koschei Library exactly-once recovery effect receipts v0.

Binds fenced recovery writes to monotonic per-epoch intent sequences and stable
idempotency keys. Retries of the same logical operation reproduce the same
receipt instead of creating a second effect. Sequence gaps, idempotency-key
reuse for different operations, stale fencing permits and lineage drift fail
closed. This module grants no external authority and performs no I/O.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib

from .library_recovery_fencing_v0 import RecoveryWritePermitV0

_CTX=b"koschei.library-recovery-exactly-once/v0\x00"

class RecoveryExactlyOnceError(ValueError): pass

@dataclass(frozen=True,slots=True)
class RecoveryEffectStateV0:
    checkpoint_digest:bytes
    writer_id:str
    epoch:int
    next_sequence:int
    committed_idempotency:tuple[tuple[bytes,bytes,bytes],...]
    state_digest:bytes
    authority:bool=False

@dataclass(frozen=True,slots=True)
class RecoveryWriteIntentV0:
    writer_id:str
    epoch:int
    checkpoint_digest:bytes
    sequence:int
    idempotency_key_digest:bytes
    operation_digest:bytes
    permit_digest:bytes
    previous_state_digest:bytes
    intent_digest:bytes
    authority:bool=False

@dataclass(frozen=True,slots=True)
class RecoveryEffectReceiptV0:
    writer_id:str
    epoch:int
    checkpoint_digest:bytes
    sequence:int
    idempotency_key_digest:bytes
    operation_digest:bytes
    effect_evidence_digest:bytes
    intent_digest:bytes
    receipt_digest:bytes
    replayed:bool
    authority:bool=False


def _d32(v:bytes,name:str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32:
        raise RecoveryExactlyOnceError(f"{name} must be exactly 32 bytes")
    return v


def make_recovery_effect_state_v0(*,permit:RecoveryWritePermitV0,next_sequence:int=1,committed_idempotency:tuple[tuple[bytes,bytes,bytes],...]=())->RecoveryEffectStateV0:
    if not isinstance(permit,RecoveryWritePermitV0) or permit.authority or not permit.allowed:
        raise RecoveryExactlyOnceError("allowed authority-free recovery write permit required")
    if not isinstance(next_sequence,int) or next_sequence<1:
        raise RecoveryExactlyOnceError("next_sequence must be positive")
    if not isinstance(committed_idempotency,tuple):
        raise RecoveryExactlyOnceError("immutable committed idempotency tuple required")
    seen=set(); normalized=[]
    for item in committed_idempotency:
        if not isinstance(item,tuple) or len(item)!=3:
            raise RecoveryExactlyOnceError("invalid idempotency record")
        key,op,receipt=item
        key=_d32(key,"idempotency_key_digest"); op=_d32(op,"operation_digest"); receipt=_d32(receipt,"receipt_digest")
        if key in seen:
            raise RecoveryExactlyOnceError("duplicate idempotency key forbidden")
        seen.add(key); normalized.append((key,op,receipt))
    h=hashlib.sha3_256(_CTX+b"state\x00"+permit.checkpoint_digest+permit.writer_id.encode()+b"\x00"+permit.epoch.to_bytes(8,"big")+next_sequence.to_bytes(8,"big"))
    for key,op,receipt in sorted(normalized,key=lambda x:x[0]):
        h.update(b"I\x00"+key+op+receipt)
    return RecoveryEffectStateV0(permit.checkpoint_digest,permit.writer_id,permit.epoch,next_sequence,tuple(sorted(normalized,key=lambda x:x[0])),h.digest(),False)


def prepare_recovery_write_intent_v0(*,permit:RecoveryWritePermitV0,state:RecoveryEffectStateV0,idempotency_key_digest:bytes,sequence:int|None=None)->RecoveryWriteIntentV0:
    if not isinstance(permit,RecoveryWritePermitV0) or permit.authority or not permit.allowed:
        raise RecoveryExactlyOnceError("allowed authority-free recovery write permit required")
    if not isinstance(state,RecoveryEffectStateV0) or state.authority:
        raise RecoveryExactlyOnceError("authority-free recovery effect state required")
    if permit.checkpoint_digest!=state.checkpoint_digest or permit.writer_id!=state.writer_id or permit.epoch!=state.epoch:
        raise RecoveryExactlyOnceError("permit/effect-state lineage drift detected")
    seq=state.next_sequence if sequence is None else sequence
    if not isinstance(seq,int) or seq!=state.next_sequence:
        raise RecoveryExactlyOnceError("write intent sequence must exactly match next_sequence")
    key=_d32(idempotency_key_digest,"idempotency_key_digest")
    if key==b"\x00"*32:
        raise RecoveryExactlyOnceError("idempotency key cannot be empty")
    op=_d32(permit.operation_digest,"operation_digest")
    for old_key,old_op,_ in state.committed_idempotency:
        if old_key==key:
            if old_op!=op:
                raise RecoveryExactlyOnceError("idempotency key reused for different operation")
            raise RecoveryExactlyOnceError("operation already committed under this idempotency key")
    material=(_CTX+b"intent\x00"+permit.writer_id.encode()+b"\x00"+permit.epoch.to_bytes(8,"big")+permit.checkpoint_digest+seq.to_bytes(8,"big")+key+op+permit.permit_digest+state.state_digest)
    return RecoveryWriteIntentV0(permit.writer_id,permit.epoch,permit.checkpoint_digest,seq,key,op,permit.permit_digest,state.state_digest,hashlib.sha3_256(material).digest(),False)


def commit_recovery_effect_v0(*,intent:RecoveryWriteIntentV0,state:RecoveryEffectStateV0,effect_evidence_digest:bytes)->tuple[RecoveryEffectReceiptV0,RecoveryEffectStateV0]:
    if not isinstance(intent,RecoveryWriteIntentV0) or intent.authority:
        raise RecoveryExactlyOnceError("authority-free recovery write intent required")
    if not isinstance(state,RecoveryEffectStateV0) or state.authority:
        raise RecoveryExactlyOnceError("authority-free recovery effect state required")
    if intent.checkpoint_digest!=state.checkpoint_digest or intent.writer_id!=state.writer_id or intent.epoch!=state.epoch or intent.previous_state_digest!=state.state_digest:
        raise RecoveryExactlyOnceError("intent/effect-state lineage drift detected")
    if intent.sequence!=state.next_sequence:
        raise RecoveryExactlyOnceError("intent sequence is stale or skipped")
    ev=_d32(effect_evidence_digest,"effect_evidence_digest")
    if ev==b"\x00"*32:
        raise RecoveryExactlyOnceError("effect evidence cannot be empty")
    for key,op,receipt_digest in state.committed_idempotency:
        if key==intent.idempotency_key_digest:
            if op!=intent.operation_digest:
                raise RecoveryExactlyOnceError("idempotency key collision across operations")
            receipt=RecoveryEffectReceiptV0(intent.writer_id,intent.epoch,intent.checkpoint_digest,intent.sequence,key,op,ev,intent.intent_digest,receipt_digest,True,False)
            return receipt,state
    material=(_CTX+b"receipt\x00"+intent.intent_digest+ev+state.state_digest)
    receipt_digest=hashlib.sha3_256(material).digest()
    receipt=RecoveryEffectReceiptV0(intent.writer_id,intent.epoch,intent.checkpoint_digest,intent.sequence,intent.idempotency_key_digest,intent.operation_digest,ev,intent.intent_digest,receipt_digest,False,False)
    records=state.committed_idempotency+((intent.idempotency_key_digest,intent.operation_digest,receipt_digest),)
    seed_permit=RecoveryWritePermitV0(state.writer_id,state.epoch,state.checkpoint_digest,b"\x00"*32,intent.operation_digest,b"\x00"*32,True,False)
    next_state=make_recovery_effect_state_v0(permit=seed_permit,next_sequence=state.next_sequence+1,committed_idempotency=records)
    return receipt,next_state


def replay_committed_effect_v0(*,state:RecoveryEffectStateV0,idempotency_key_digest:bytes,operation_digest:bytes)->RecoveryEffectReceiptV0:
    if not isinstance(state,RecoveryEffectStateV0) or state.authority:
        raise RecoveryExactlyOnceError("authority-free recovery effect state required")
    key=_d32(idempotency_key_digest,"idempotency_key_digest"); op=_d32(operation_digest,"operation_digest")
    for old_key,old_op,receipt_digest in state.committed_idempotency:
        if old_key==key:
            if old_op!=op:
                raise RecoveryExactlyOnceError("idempotency key reused for different operation")
            return RecoveryEffectReceiptV0(state.writer_id,state.epoch,state.checkpoint_digest,0,key,op,b"\x00"*32,b"\x00"*32,receipt_digest,True,False)
    raise RecoveryExactlyOnceError("idempotency key not previously committed")
