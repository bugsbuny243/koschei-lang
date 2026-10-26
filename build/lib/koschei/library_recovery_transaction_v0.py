"""Koschei Library atomic recovery transaction engine v0.

Binds an executable recovery-priority plan into a staged transaction. Recovery
steps are prepared and verified before a terminal commit/abort receipt is
derived. Partial application never becomes a successful transaction state.
This module grants no runtime authority and performs no external action.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib

from .library_policy_conflict_resolution_v0 import RecoveryPriorityPlanV0

_CTX=b"koschei.library-recovery-transaction/v0\x00"

class RecoveryTransactionError(ValueError): pass

class RecoveryTransactionState(str,Enum):
    PREPARED="prepared"
    COMMITTED="committed"
    ABORTED="aborted"

@dataclass(frozen=True,slots=True)
class RecoveryStepPreparationV0:
    step_id:str
    action_digest:bytes
    precondition_digest:bytes
    evidence_digest:bytes
    ready:bool

@dataclass(frozen=True,slots=True)
class RecoveryTransactionV0:
    graph_digest:bytes
    recovery_plan_digest:bytes
    ordered_step_ids:tuple[str,...]
    prepared_step_ids:tuple[str,...]
    preparation_digest:bytes
    state:RecoveryTransactionState
    authority:bool=False

@dataclass(frozen=True,slots=True)
class RecoveryTransactionReceiptV0:
    graph_digest:bytes
    recovery_plan_digest:bytes
    preparation_digest:bytes
    final_state:RecoveryTransactionState
    applied_step_ids:tuple[str,...]
    terminal_evidence_digest:bytes
    receipt_digest:bytes
    authority:bool=False


def _d32(v:bytes,name:str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32:
        raise RecoveryTransactionError(f"{name} must be exactly 32 bytes")
    return v


def prepare_recovery_transaction_v0(*,plan:RecoveryPriorityPlanV0,preparations:tuple[RecoveryStepPreparationV0,...])->RecoveryTransactionV0:
    if not isinstance(plan,RecoveryPriorityPlanV0) or plan.authority or not plan.executable:
        raise RecoveryTransactionError("executable authority-free recovery plan required")
    if not isinstance(preparations,tuple) or not preparations:
        raise RecoveryTransactionError("non-empty immutable preparation tuple required")
    expected=tuple(plan.ordered_step_ids)
    by_id={}; seen_actions=set()
    for p in preparations:
        if not isinstance(p,RecoveryStepPreparationV0) or not p.step_id or p.step_id in by_id:
            raise RecoveryTransactionError("invalid or duplicate step preparation")
        ad=_d32(p.action_digest,"action_digest")
        pc=_d32(p.precondition_digest,"precondition_digest")
        ev=_d32(p.evidence_digest,"evidence_digest")
        if pc==b"\x00"*32 or ev==b"\x00"*32:
            raise RecoveryTransactionError("precondition/evidence cannot be empty")
        if ad in seen_actions:
            raise RecoveryTransactionError("duplicate prepared action digest forbidden")
        seen_actions.add(ad); by_id[p.step_id]=p
    if set(by_id)!=set(expected):
        raise RecoveryTransactionError("every ordered recovery step must be prepared exactly once")
    if any(not by_id[sid].ready for sid in expected):
        raise RecoveryTransactionError("all recovery steps must be ready before transaction preparation")

    h=hashlib.sha3_256(_CTX+b"prepare\x00"+plan.graph_digest+_d32(plan.plan_digest,"plan_digest"))
    for sid in expected:
        p=by_id[sid]
        h.update(b"S\x00"+sid.encode()+b"\x00"+p.action_digest+p.precondition_digest+p.evidence_digest+b"\x01")
    digest=h.digest()
    return RecoveryTransactionV0(
        plan.graph_digest,plan.plan_digest,expected,expected,digest,
        RecoveryTransactionState.PREPARED,False
    )


def finalize_recovery_transaction_v0(*,transaction:RecoveryTransactionV0,plan:RecoveryPriorityPlanV0,applied_step_ids:tuple[str,...],terminal_evidence_digest:bytes,commit:bool)->RecoveryTransactionReceiptV0:
    if not isinstance(transaction,RecoveryTransactionV0) or transaction.authority:
        raise RecoveryTransactionError("authority-free recovery transaction required")
    if transaction.state is not RecoveryTransactionState.PREPARED:
        raise RecoveryTransactionError("only prepared transaction may finalize")
    if not isinstance(plan,RecoveryPriorityPlanV0) or plan.authority or not plan.executable:
        raise RecoveryTransactionError("executable authority-free recovery plan required")
    if transaction.graph_digest!=plan.graph_digest or transaction.recovery_plan_digest!=plan.plan_digest or transaction.ordered_step_ids!=plan.ordered_step_ids:
        raise RecoveryTransactionError("transaction/recovery plan drift detected")
    if not isinstance(applied_step_ids,tuple):
        raise RecoveryTransactionError("immutable applied-step tuple required")
    if len(applied_step_ids)!=len(set(applied_step_ids)):
        raise RecoveryTransactionError("duplicate applied recovery step forbidden")
    ev=_d32(terminal_evidence_digest,"terminal_evidence_digest")
    if ev==b"\x00"*32:
        raise RecoveryTransactionError("terminal evidence cannot be empty")

    expected=transaction.ordered_step_ids
    if commit:
        if applied_step_ids!=expected:
            raise RecoveryTransactionError("commit requires exact ordered completion of every recovery step")
        state=RecoveryTransactionState.COMMITTED
    else:
        # Abort may record a valid prefix only; arbitrary reordering or skipping is forbidden.
        if applied_step_ids!=expected[:len(applied_step_ids)]:
            raise RecoveryTransactionError("abort may only record an ordered recovery prefix")
        state=RecoveryTransactionState.ABORTED

    h=hashlib.sha3_256(
        _CTX+b"finalize\x00"+transaction.graph_digest+transaction.recovery_plan_digest
        +transaction.preparation_digest+state.value.encode()+ev
    )
    for sid in applied_step_ids:
        h.update(b"A\x00"+sid.encode()+b"\x00")
    return RecoveryTransactionReceiptV0(
        transaction.graph_digest,transaction.recovery_plan_digest,
        transaction.preparation_digest,state,applied_step_ids,ev,h.digest(),False
    )


def verify_recovery_transaction_receipt_v0(*,receipt:RecoveryTransactionReceiptV0,transaction:RecoveryTransactionV0,plan:RecoveryPriorityPlanV0)->bool:
    if not isinstance(receipt,RecoveryTransactionReceiptV0) or receipt.authority:
        return False
    try:
        rebuilt=finalize_recovery_transaction_v0(
            transaction=transaction,
            plan=plan,
            applied_step_ids=receipt.applied_step_ids,
            terminal_evidence_digest=receipt.terminal_evidence_digest,
            commit=receipt.final_state is RecoveryTransactionState.COMMITTED,
        )
    except RecoveryTransactionError:
        return False
    return rebuilt==receipt
