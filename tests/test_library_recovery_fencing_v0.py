import hashlib
import pytest

from koschei.library_recovery_fencing_v0 import (
    RecoveryFencingError,
    authorize_recovery_write_v0,
    issue_recovery_lease_v0,
    make_recovery_fence_state_v0,
)
from koschei.library_recovery_replica_quorum_v0 import RecoveryCheckpointV0


def d(label: str) -> bytes:
    return hashlib.sha3_256(label.encode()).digest()


def checkpoint(tag: str = "a") -> RecoveryCheckpointV0:
    return RecoveryCheckpointV0(
        graph_digest=d("graph"),
        recovery_plan_digest=d("plan"),
        preparation_digest=d("prep"),
        canonical_journal_digest=d("journal-" + tag),
        canonical_sequence=3,
        agreeing_replica_ids=("r1", "r2"),
        divergent_replica_ids=(),
        quorum_threshold=2,
        checkpoint_digest=d("checkpoint-" + tag),
        durable=True,
        split_brain=False,
        authority=False,
    )


def test_single_writer_epoch_fences_stale_leader():
    cp=checkpoint()
    state=make_recovery_fence_state_v0(checkpoint=cp)
    lease1,state1=issue_recovery_lease_v0(
        checkpoint=cp,state=state,writer_id="writer-a",next_epoch=1,
        issued_tick=10,expires_tick=20,entropy_digest=d("entropy-1"),
    )
    p1=authorize_recovery_write_v0(
        checkpoint=cp,state=state1,lease=lease1,current_tick=11,operation_digest=d("op-1")
    )
    assert p1.allowed and p1.epoch==1

    lease2,state2=issue_recovery_lease_v0(
        checkpoint=cp,state=state1,writer_id="writer-b",next_epoch=2,
        issued_tick=12,expires_tick=22,entropy_digest=d("entropy-2"),
    )
    with pytest.raises(RecoveryFencingError,match="stale recovery leader"):
        authorize_recovery_write_v0(
            checkpoint=cp,state=state2,lease=lease1,current_tick=13,operation_digest=d("late-old-write")
        )
    assert authorize_recovery_write_v0(
        checkpoint=cp,state=state2,lease=lease2,current_tick=13,operation_digest=d("op-2")
    ).allowed


def test_expired_lease_fails_closed():
    cp=checkpoint(); state=make_recovery_fence_state_v0(checkpoint=cp)
    lease,state=issue_recovery_lease_v0(
        checkpoint=cp,state=state,writer_id="writer-a",next_epoch=1,
        issued_tick=100,expires_tick=105,entropy_digest=d("entropy"),
    )
    with pytest.raises(RecoveryFencingError,match="not currently valid"):
        authorize_recovery_write_v0(
            checkpoint=cp,state=state,lease=lease,current_tick=105,operation_digest=d("op")
        )


def test_checkpoint_drift_rejects_old_lease():
    cp1=checkpoint("a"); cp2=checkpoint("b")
    state=make_recovery_fence_state_v0(checkpoint=cp1)
    lease,state=issue_recovery_lease_v0(
        checkpoint=cp1,state=state,writer_id="writer-a",next_epoch=1,
        issued_tick=1,expires_tick=10,entropy_digest=d("entropy"),
    )
    with pytest.raises(RecoveryFencingError):
        authorize_recovery_write_v0(
            checkpoint=cp2,state=state,lease=lease,current_tick=2,operation_digest=d("op")
        )


def test_epoch_must_advance_and_lease_window_is_bounded():
    cp=checkpoint(); state=make_recovery_fence_state_v0(checkpoint=cp)
    _,state1=issue_recovery_lease_v0(
        checkpoint=cp,state=state,writer_id="writer-a",next_epoch=1,
        issued_tick=1,expires_tick=10,entropy_digest=d("entropy-1"),
    )
    with pytest.raises(RecoveryFencingError,match="advance monotonically"):
        issue_recovery_lease_v0(
            checkpoint=cp,state=state1,writer_id="writer-b",next_epoch=1,
            issued_tick=2,expires_tick=9,entropy_digest=d("entropy-2"),
        )
    with pytest.raises(RecoveryFencingError,match="hard safety window"):
        issue_recovery_lease_v0(
            checkpoint=cp,state=state1,writer_id="writer-b",next_epoch=2,
            issued_tick=2,expires_tick=2000,entropy_digest=d("entropy-3"),
        )


def test_empty_operation_digest_rejected():
    cp=checkpoint(); state=make_recovery_fence_state_v0(checkpoint=cp)
    lease,state=issue_recovery_lease_v0(
        checkpoint=cp,state=state,writer_id="writer-a",next_epoch=1,
        issued_tick=1,expires_tick=10,entropy_digest=d("entropy"),
    )
    with pytest.raises(RecoveryFencingError,match="operation digest cannot be empty"):
        authorize_recovery_write_v0(
            checkpoint=cp,state=state,lease=lease,current_tick=2,operation_digest=b"\x00"*32
        )
