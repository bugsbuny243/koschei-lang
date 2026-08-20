import hashlib
import pytest

from koschei.library_policy_conflict_resolution_v0 import RecoveryPriorityPlanV0
from koschei.library_recovery_transaction_v0 import (
    RecoveryStepPreparationV0,
    RecoveryTransactionError,
    RecoveryTransactionState,
    prepare_recovery_transaction_v0,
    finalize_recovery_transaction_v0,
    verify_recovery_transaction_receipt_v0,
)


def d(tag: str) -> bytes:
    return hashlib.sha3_256(tag.encode()).digest()


def plan() -> RecoveryPriorityPlanV0:
    return RecoveryPriorityPlanV0(
        graph_digest=d("graph"),
        containment_digest=d("containment"),
        ordered_step_ids=("s1", "s2", "s3"),
        dependency_edges=(("s1", "s2"), ("s2", "s3")),
        deferred_step_ids=(),
        plan_digest=d("plan"),
        executable=True,
        authority=False,
    )


def preparations():
    return (
        RecoveryStepPreparationV0("s1", d("a1"), d("p1"), d("e1"), True),
        RecoveryStepPreparationV0("s2", d("a2"), d("p2"), d("e2"), True),
        RecoveryStepPreparationV0("s3", d("a3"), d("p3"), d("e3"), True),
    )


def test_commit_requires_exact_full_order():
    p=plan()
    tx=prepare_recovery_transaction_v0(plan=p,preparations=preparations())
    r=finalize_recovery_transaction_v0(
        transaction=tx,plan=p,applied_step_ids=("s1","s2","s3"),
        terminal_evidence_digest=d("done"),commit=True,
    )
    assert r.final_state is RecoveryTransactionState.COMMITTED
    assert verify_recovery_transaction_receipt_v0(receipt=r,transaction=tx,plan=p)


def test_partial_commit_fails_closed():
    p=plan(); tx=prepare_recovery_transaction_v0(plan=p,preparations=preparations())
    with pytest.raises(RecoveryTransactionError):
        finalize_recovery_transaction_v0(
            transaction=tx,plan=p,applied_step_ids=("s1","s2"),
            terminal_evidence_digest=d("partial"),commit=True,
        )


def test_abort_accepts_only_ordered_prefix():
    p=plan(); tx=prepare_recovery_transaction_v0(plan=p,preparations=preparations())
    r=finalize_recovery_transaction_v0(
        transaction=tx,plan=p,applied_step_ids=("s1",),
        terminal_evidence_digest=d("abort"),commit=False,
    )
    assert r.final_state is RecoveryTransactionState.ABORTED
    with pytest.raises(RecoveryTransactionError):
        finalize_recovery_transaction_v0(
            transaction=tx,plan=p,applied_step_ids=("s2",),
            terminal_evidence_digest=d("bad-abort"),commit=False,
        )


def test_not_ready_step_prevents_prepare():
    p=plan(); ps=list(preparations())
    ps[1]=RecoveryStepPreparationV0("s2", d("a2"), d("p2"), d("e2"), False)
    with pytest.raises(RecoveryTransactionError):
        prepare_recovery_transaction_v0(plan=p,preparations=tuple(ps))


def test_plan_drift_rejected():
    p=plan(); tx=prepare_recovery_transaction_v0(plan=p,preparations=preparations())
    drift=RecoveryPriorityPlanV0(
        p.graph_digest,p.containment_digest,p.ordered_step_ids,p.dependency_edges,
        p.deferred_step_ids,d("different-plan"),True,False,
    )
    with pytest.raises(RecoveryTransactionError):
        finalize_recovery_transaction_v0(
            transaction=tx,plan=drift,applied_step_ids=p.ordered_step_ids,
            terminal_evidence_digest=d("done"),commit=True,
        )


def test_tampered_receipt_fails_verification():
    p=plan(); tx=prepare_recovery_transaction_v0(plan=p,preparations=preparations())
    r=finalize_recovery_transaction_v0(
        transaction=tx,plan=p,applied_step_ids=p.ordered_step_ids,
        terminal_evidence_digest=d("done"),commit=True,
    )
    bad=type(r)(
        r.graph_digest,r.recovery_plan_digest,r.preparation_digest,r.final_state,
        r.applied_step_ids,r.terminal_evidence_digest,d("tampered"),False,
    )
    assert not verify_recovery_transaction_receipt_v0(receipt=bad,transaction=tx,plan=p)
