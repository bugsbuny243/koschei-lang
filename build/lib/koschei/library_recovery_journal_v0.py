"""Koschei Library recovery journal v0.

Provides crash-consistent, append-only recovery transaction journaling with
hash chaining, monotonic sequence numbers, terminal-state sealing and safe
resume classification. This layer grants no runtime authority.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib

from .library_recovery_transaction_v0 import RecoveryTransactionV0, RecoveryTransactionReceiptV0, RecoveryTransactionState

_CTX=b"koschei.library-recovery-journal/v0\x00"

class RecoveryJournalError(ValueError): pass

class JournalEventKind(str,Enum):
    PREPARED="prepared"
    STEP_APPLIED="step_applied"
    COMMITTED="committed"
    ABORTED="aborted"

@dataclass(frozen=True,slots=True)
class RecoveryJournalEntryV0:
    sequence:int
    kind:JournalEventKind
    step_id:str|None
    evidence_digest:bytes
    previous_entry_digest:bytes
    entry_digest:bytes

@dataclass(frozen=True,slots=True)
class RecoveryJournalV0:
    graph_digest:bytes
    recovery_plan_digest:bytes
    preparation_digest:bytes
    entries:tuple[RecoveryJournalEntryV0,...]
    journal_digest:bytes
    terminal:bool
    authority:bool=False

@dataclass(frozen=True,slots=True)
class RecoveryResumeStateV0:
    applied_step_ids:tuple[str,...]
    next_step_id:str|None
    terminal_state:RecoveryTransactionState|None
    resume_digest:bytes
    resumable:bool
    authority:bool=False


def _d32(v:bytes,name:str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32: raise RecoveryJournalError(f"{name} must be exactly 32 bytes")
    return v


def _entry_digest(*,sequence:int,kind:JournalEventKind,step_id:str|None,evidence_digest:bytes,previous_entry_digest:bytes)->bytes:
    if sequence<1: raise RecoveryJournalError("journal sequence must be positive")
    ev=_d32(evidence_digest,"evidence_digest"); prev=_d32(previous_entry_digest,"previous_entry_digest")
    sid=b"" if step_id is None else step_id.encode()
    return hashlib.sha3_256(_CTX+b"entry\x00"+sequence.to_bytes(8,"big")+kind.value.encode()+b"\x00"+len(sid).to_bytes(2,"big")+sid+ev+prev).digest()


def open_recovery_journal_v0(*,transaction:RecoveryTransactionV0,evidence_digest:bytes)->RecoveryJournalV0:
    if not isinstance(transaction,RecoveryTransactionV0) or transaction.authority or transaction.state is not RecoveryTransactionState.PREPARED:
        raise RecoveryJournalError("prepared authority-free recovery transaction required")
    ev=_d32(evidence_digest,"evidence_digest")
    if ev==b"\x00"*32: raise RecoveryJournalError("journal open evidence cannot be empty")
    prev=b"\x00"*32
    ed=_entry_digest(sequence=1,kind=JournalEventKind.PREPARED,step_id=None,evidence_digest=ev,previous_entry_digest=prev)
    entry=RecoveryJournalEntryV0(1,JournalEventKind.PREPARED,None,ev,prev,ed)
    jd=hashlib.sha3_256(_CTX+b"journal\x00"+transaction.graph_digest+transaction.recovery_plan_digest+transaction.preparation_digest+ed).digest()
    return RecoveryJournalV0(transaction.graph_digest,transaction.recovery_plan_digest,transaction.preparation_digest,(entry,),jd,False,False)


def append_recovery_step_v0(*,journal:RecoveryJournalV0,transaction:RecoveryTransactionV0,step_id:str,evidence_digest:bytes)->RecoveryJournalV0:
    if not isinstance(journal,RecoveryJournalV0) or journal.authority or journal.terminal: raise RecoveryJournalError("open authority-free journal required")
    if transaction.graph_digest!=journal.graph_digest or transaction.recovery_plan_digest!=journal.recovery_plan_digest or transaction.preparation_digest!=journal.preparation_digest:
        raise RecoveryJournalError("journal/transaction drift detected")
    applied=tuple(e.step_id for e in journal.entries if e.kind is JournalEventKind.STEP_APPLIED)
    expected=transaction.ordered_step_ids
    if len(applied)>=len(expected) or step_id!=expected[len(applied)]: raise RecoveryJournalError("recovery steps must journal in canonical order")
    ev=_d32(evidence_digest,"evidence_digest")
    if ev==b"\x00"*32: raise RecoveryJournalError("step evidence cannot be empty")
    prev=journal.entries[-1].entry_digest; seq=len(journal.entries)+1
    ed=_entry_digest(sequence=seq,kind=JournalEventKind.STEP_APPLIED,step_id=step_id,evidence_digest=ev,previous_entry_digest=prev)
    entry=RecoveryJournalEntryV0(seq,JournalEventKind.STEP_APPLIED,step_id,ev,prev,ed)
    entries=journal.entries+(entry,)
    jd=hashlib.sha3_256(journal.journal_digest+ed).digest()
    return RecoveryJournalV0(journal.graph_digest,journal.recovery_plan_digest,journal.preparation_digest,entries,jd,False,False)


def seal_recovery_journal_v0(*,journal:RecoveryJournalV0,receipt:RecoveryTransactionReceiptV0)->RecoveryJournalV0:
    if not isinstance(journal,RecoveryJournalV0) or journal.authority or journal.terminal: raise RecoveryJournalError("open journal required")
    if receipt.graph_digest!=journal.graph_digest or receipt.recovery_plan_digest!=journal.recovery_plan_digest or receipt.preparation_digest!=journal.preparation_digest:
        raise RecoveryJournalError("receipt/journal drift detected")
    applied=tuple(e.step_id for e in journal.entries if e.kind is JournalEventKind.STEP_APPLIED)
    if applied!=receipt.applied_step_ids: raise RecoveryJournalError("journaled steps differ from terminal receipt")
    kind=JournalEventKind.COMMITTED if receipt.final_state is RecoveryTransactionState.COMMITTED else JournalEventKind.ABORTED
    prev=journal.entries[-1].entry_digest; seq=len(journal.entries)+1
    ed=_entry_digest(sequence=seq,kind=kind,step_id=None,evidence_digest=receipt.terminal_evidence_digest,previous_entry_digest=prev)
    entry=RecoveryJournalEntryV0(seq,kind,None,receipt.terminal_evidence_digest,prev,ed)
    return RecoveryJournalV0(journal.graph_digest,journal.recovery_plan_digest,journal.preparation_digest,journal.entries+(entry,),hashlib.sha3_256(journal.journal_digest+receipt.receipt_digest+ed).digest(),True,False)


def classify_recovery_resume_v0(*,journal:RecoveryJournalV0,transaction:RecoveryTransactionV0)->RecoveryResumeStateV0:
    if not isinstance(journal,RecoveryJournalV0) or journal.authority: raise RecoveryJournalError("authority-free journal required")
    if transaction.graph_digest!=journal.graph_digest or transaction.recovery_plan_digest!=journal.recovery_plan_digest or transaction.preparation_digest!=journal.preparation_digest:
        raise RecoveryJournalError("journal/transaction drift detected")
    prev=b"\x00"*32
    terminal=None; applied=[]
    for i,e in enumerate(journal.entries,1):
        if e.sequence!=i or e.previous_entry_digest!=prev: raise RecoveryJournalError("journal chain/sequence corruption")
        if _entry_digest(sequence=e.sequence,kind=e.kind,step_id=e.step_id,evidence_digest=e.evidence_digest,previous_entry_digest=e.previous_entry_digest)!=e.entry_digest:
            raise RecoveryJournalError("journal entry digest mismatch")
        prev=e.entry_digest
        if e.kind is JournalEventKind.STEP_APPLIED: applied.append(e.step_id)
        elif e.kind is JournalEventKind.COMMITTED: terminal=RecoveryTransactionState.COMMITTED
        elif e.kind is JournalEventKind.ABORTED: terminal=RecoveryTransactionState.ABORTED
    if tuple(applied)!=transaction.ordered_step_ids[:len(applied)]: raise RecoveryJournalError("journal applied-step prefix invalid")
    next_step=None if terminal or len(applied)==len(transaction.ordered_step_ids) else transaction.ordered_step_ids[len(applied)]
    resumable=terminal is None
    digest=hashlib.sha3_256(_CTX+b"resume\x00"+journal.journal_digest+(b"-" if terminal is None else terminal.value.encode())+(b"" if next_step is None else next_step.encode())).digest()
    return RecoveryResumeStateV0(tuple(applied),next_step,terminal,digest,resumable,False)
