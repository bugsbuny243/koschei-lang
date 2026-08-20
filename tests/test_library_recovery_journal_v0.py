import hashlib
import pytest

from koschei.library_recovery_transaction_v0 import (
    RecoveryTransactionV0, RecoveryTransactionReceiptV0, RecoveryTransactionState,
)
from koschei.library_recovery_journal_v0 import (
    RecoveryJournalError, open_recovery_journal_v0, append_recovery_step_v0,
    seal_recovery_journal_v0, classify_recovery_resume_v0,
)


def d(tag: bytes) -> bytes:
    return hashlib.sha3_256(tag).digest()


def tx():
    return RecoveryTransactionV0(d(b"g"),d(b"p"),("a","b"),("a","b"),d(b"prep"),RecoveryTransactionState.PREPARED,False)


def receipt(t, state, applied):
    return RecoveryTransactionReceiptV0(t.graph_digest,t.recovery_plan_digest,t.preparation_digest,state,applied,d(b"term"),d(b"r"+state.value.encode()),False)


def test_resume_after_crash_tracks_next_step():
    t=tx(); j=open_recovery_journal_v0(transaction=t,evidence_digest=d(b"open"))
    j=append_recovery_step_v0(journal=j,transaction=t,step_id="a",evidence_digest=d(b"a"))
    s=classify_recovery_resume_v0(journal=j,transaction=t)
    assert s.applied_step_ids==("a",) and s.next_step_id=="b" and s.resumable


def test_out_of_order_step_fails_closed():
    t=tx(); j=open_recovery_journal_v0(transaction=t,evidence_digest=d(b"open"))
    with pytest.raises(RecoveryJournalError):
        append_recovery_step_v0(journal=j,transaction=t,step_id="b",evidence_digest=d(b"b"))


def test_commit_seals_and_is_not_resumable():
    t=tx(); j=open_recovery_journal_v0(transaction=t,evidence_digest=d(b"open"))
    j=append_recovery_step_v0(journal=j,transaction=t,step_id="a",evidence_digest=d(b"a"))
    j=append_recovery_step_v0(journal=j,transaction=t,step_id="b",evidence_digest=d(b"b"))
    j=seal_recovery_journal_v0(journal=j,receipt=receipt(t,RecoveryTransactionState.COMMITTED,("a","b")))
    s=classify_recovery_resume_v0(journal=j,transaction=t)
    assert s.terminal_state is RecoveryTransactionState.COMMITTED and not s.resumable


def test_abort_requires_same_applied_prefix():
    t=tx(); j=open_recovery_journal_v0(transaction=t,evidence_digest=d(b"open"))
    j=append_recovery_step_v0(journal=j,transaction=t,step_id="a",evidence_digest=d(b"a"))
    with pytest.raises(RecoveryJournalError):
        seal_recovery_journal_v0(journal=j,receipt=receipt(t,RecoveryTransactionState.ABORTED,()))


def test_chain_tamper_detected():
    from dataclasses import replace
    t=tx(); j=open_recovery_journal_v0(transaction=t,evidence_digest=d(b"open"))
    bad_entry=replace(j.entries[0], evidence_digest=d(b"evil"))
    bad=replace(j, entries=(bad_entry,))
    with pytest.raises(RecoveryJournalError):
        classify_recovery_resume_v0(journal=bad,transaction=t)
