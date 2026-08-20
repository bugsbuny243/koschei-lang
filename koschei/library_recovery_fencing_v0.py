"""Koschei Library single-writer recovery fencing v0.

Binds recovery writers to monotonically increasing epochs and fencing tokens.
Only the current lease holder may derive a write permit for the current durable
checkpoint. Stale leaders, replayed tokens, expired leases and checkpoint drift
fail closed. This module grants no external authority and performs no I/O.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib

from .library_recovery_replica_quorum_v0 import RecoveryCheckpointV0

_CTX=b"koschei.library-recovery-fencing/v0\x00"

class RecoveryFencingError(ValueError): pass

@dataclass(frozen=True,slots=True)
class RecoveryLeaseV0:
    writer_id:str
    graph_digest:bytes
    recovery_plan_digest:bytes
    checkpoint_digest:bytes
    epoch:int
    issued_tick:int
    expires_tick:int
    fencing_token:bytes
    lease_digest:bytes
    authority:bool=False

@dataclass(frozen=True,slots=True)
class RecoveryFenceStateV0:
    graph_digest:bytes
    recovery_plan_digest:bytes
    current_epoch:int
    highest_fencing_token_digest:bytes
    state_digest:bytes
    authority:bool=False

@dataclass(frozen=True,slots=True)
class RecoveryWritePermitV0:
    writer_id:str
    epoch:int
    checkpoint_digest:bytes
    fencing_token_digest:bytes
    operation_digest:bytes
    permit_digest:bytes
    allowed:bool
    authority:bool=False


def _d32(v:bytes,name:str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32:
        raise RecoveryFencingError(f"{name} must be exactly 32 bytes")
    return v


def make_recovery_fence_state_v0(*,checkpoint:RecoveryCheckpointV0,current_epoch:int=0,highest_fencing_token_digest:bytes|None=None)->RecoveryFenceStateV0:
    if not isinstance(checkpoint,RecoveryCheckpointV0) or checkpoint.authority or not checkpoint.durable or checkpoint.split_brain:
        raise RecoveryFencingError("durable split-brain-free recovery checkpoint required")
    if not isinstance(current_epoch,int) or current_epoch<0:
        raise RecoveryFencingError("current_epoch must be non-negative")
    highest=b"\x00"*32 if highest_fencing_token_digest is None else _d32(highest_fencing_token_digest,"highest_fencing_token_digest")
    h=hashlib.sha3_256(_CTX+b"state\x00"+checkpoint.graph_digest+checkpoint.recovery_plan_digest+current_epoch.to_bytes(8,"big")+highest).digest()
    return RecoveryFenceStateV0(checkpoint.graph_digest,checkpoint.recovery_plan_digest,current_epoch,highest,h,False)


def issue_recovery_lease_v0(*,checkpoint:RecoveryCheckpointV0,state:RecoveryFenceStateV0,writer_id:str,next_epoch:int,issued_tick:int,expires_tick:int,entropy_digest:bytes)->tuple[RecoveryLeaseV0,RecoveryFenceStateV0]:
    if not isinstance(checkpoint,RecoveryCheckpointV0) or checkpoint.authority or not checkpoint.durable or checkpoint.split_brain:
        raise RecoveryFencingError("durable split-brain-free recovery checkpoint required")
    if not isinstance(state,RecoveryFenceStateV0) or state.authority:
        raise RecoveryFencingError("authority-free recovery fence state required")
    if checkpoint.graph_digest!=state.graph_digest or checkpoint.recovery_plan_digest!=state.recovery_plan_digest:
        raise RecoveryFencingError("checkpoint/fence-state drift detected")
    if not writer_id or len(writer_id)>96:
        raise RecoveryFencingError("invalid writer identity")
    if not isinstance(next_epoch,int) or next_epoch<=state.current_epoch:
        raise RecoveryFencingError("lease epoch must advance monotonically")
    if not isinstance(issued_tick,int) or not isinstance(expires_tick,int) or issued_tick<0 or expires_tick<=issued_tick:
        raise RecoveryFencingError("invalid lease lifetime")
    if expires_tick-issued_tick>1024:
        raise RecoveryFencingError("lease lifetime exceeds hard safety window")
    entropy=_d32(entropy_digest,"entropy_digest")
    if entropy==b"\x00"*32:
        raise RecoveryFencingError("lease entropy cannot be empty")
    token=hashlib.sha3_256(_CTX+b"token\x00"+writer_id.encode()+b"\x00"+checkpoint.checkpoint_digest+next_epoch.to_bytes(8,"big")+issued_tick.to_bytes(8,"big")+expires_tick.to_bytes(8,"big")+entropy+state.state_digest).digest()
    material=_CTX+b"lease\x00"+writer_id.encode()+b"\x00"+checkpoint.graph_digest+checkpoint.recovery_plan_digest+checkpoint.checkpoint_digest+next_epoch.to_bytes(8,"big")+issued_tick.to_bytes(8,"big")+expires_tick.to_bytes(8,"big")+token
    lease=RecoveryLeaseV0(writer_id,checkpoint.graph_digest,checkpoint.recovery_plan_digest,checkpoint.checkpoint_digest,next_epoch,issued_tick,expires_tick,token,hashlib.sha3_256(material).digest(),False)
    token_digest=hashlib.sha3_256(token).digest()
    h=hashlib.sha3_256(_CTX+b"state\x00"+state.graph_digest+state.recovery_plan_digest+next_epoch.to_bytes(8,"big")+token_digest).digest()
    return lease,RecoveryFenceStateV0(state.graph_digest,state.recovery_plan_digest,next_epoch,token_digest,h,False)


def authorize_recovery_write_v0(*,checkpoint:RecoveryCheckpointV0,state:RecoveryFenceStateV0,lease:RecoveryLeaseV0,current_tick:int,operation_digest:bytes)->RecoveryWritePermitV0:
    if not isinstance(checkpoint,RecoveryCheckpointV0) or checkpoint.authority or not checkpoint.durable or checkpoint.split_brain:
        raise RecoveryFencingError("durable split-brain-free recovery checkpoint required")
    if not isinstance(state,RecoveryFenceStateV0) or state.authority:
        raise RecoveryFencingError("authority-free recovery fence state required")
    if not isinstance(lease,RecoveryLeaseV0) or lease.authority:
        raise RecoveryFencingError("authority-free recovery lease required")
    if checkpoint.graph_digest!=state.graph_digest or checkpoint.recovery_plan_digest!=state.recovery_plan_digest:
        raise RecoveryFencingError("checkpoint/fence-state drift detected")
    if lease.graph_digest!=checkpoint.graph_digest or lease.recovery_plan_digest!=checkpoint.recovery_plan_digest or lease.checkpoint_digest!=checkpoint.checkpoint_digest:
        raise RecoveryFencingError("lease bound to different recovery reality")
    if lease.epoch!=state.current_epoch:
        raise RecoveryFencingError("stale recovery leader fenced out")
    if not isinstance(current_tick,int) or current_tick<lease.issued_tick or current_tick>=lease.expires_tick:
        raise RecoveryFencingError("recovery lease not currently valid")
    token_digest=hashlib.sha3_256(_d32(lease.fencing_token,"fencing_token")).digest()
    if token_digest!=state.highest_fencing_token_digest:
        raise RecoveryFencingError("fencing token is not current")
    op=_d32(operation_digest,"operation_digest")
    if op==b"\x00"*32:
        raise RecoveryFencingError("operation digest cannot be empty")
    material=_CTX+b"permit\x00"+lease.writer_id.encode()+b"\x00"+lease.epoch.to_bytes(8,"big")+checkpoint.checkpoint_digest+token_digest+op+lease.lease_digest+state.state_digest
    return RecoveryWritePermitV0(lease.writer_id,lease.epoch,checkpoint.checkpoint_digest,token_digest,op,hashlib.sha3_256(material).digest(),True,False)
