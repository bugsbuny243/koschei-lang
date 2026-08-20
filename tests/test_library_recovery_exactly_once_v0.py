import hashlib
import pytest

from koschei.library_recovery_fencing_v0 import RecoveryWritePermitV0
from koschei.library_recovery_exactly_once_v0 import (
    RecoveryExactlyOnceError,
    make_recovery_effect_state_v0,
    prepare_recovery_write_intent_v0,
    commit_recovery_effect_v0,
    replay_committed_effect_v0,
)


def d(label:str)->bytes:
    return hashlib.sha3_256(label.encode()).digest()


def permit(op:str="op-a", epoch:int=7)->RecoveryWritePermitV0:
    return RecoveryWritePermitV0(
        writer_id="writer-a",
        epoch=epoch,
        checkpoint_digest=d("checkpoint"),
        fencing_token_digest=d("fence"),
        operation_digest=d(op),
        permit_digest=d("permit-"+op),
        allowed=True,
        authority=False,
    )


def test_commit_advances_sequence_and_records_idempotency():
    p=permit(); state=make_recovery_effect_state_v0(permit=p)
    intent=prepare_recovery_write_intent_v0(permit=p,state=state,idempotency_key_digest=d("idem-a"))
    receipt,next_state=commit_recovery_effect_v0(intent=intent,state=state,effect_evidence_digest=d("effect-a"))
    assert receipt.replayed is False
    assert receipt.sequence==1
    assert next_state.next_sequence==2
    assert next_state.committed_idempotency[0][0]==d("idem-a")


def test_sequence_gap_rejected():
    p=permit(); state=make_recovery_effect_state_v0(permit=p)
    with pytest.raises(RecoveryExactlyOnceError):
        prepare_recovery_write_intent_v0(permit=p,state=state,idempotency_key_digest=d("idem-a"),sequence=2)


def test_same_idempotency_key_cannot_prepare_second_effect():
    p=permit(); state=make_recovery_effect_state_v0(permit=p)
    intent=prepare_recovery_write_intent_v0(permit=p,state=state,idempotency_key_digest=d("idem-a"))
    _,state2=commit_recovery_effect_v0(intent=intent,state=state,effect_evidence_digest=d("effect-a"))
    p2=permit()
    with pytest.raises(RecoveryExactlyOnceError):
        prepare_recovery_write_intent_v0(permit=p2,state=state2,idempotency_key_digest=d("idem-a"))


def test_idempotency_key_reuse_for_different_operation_rejected():
    p=permit(); state=make_recovery_effect_state_v0(permit=p)
    intent=prepare_recovery_write_intent_v0(permit=p,state=state,idempotency_key_digest=d("idem-a"))
    _,state2=commit_recovery_effect_v0(intent=intent,state=state,effect_evidence_digest=d("effect-a"))
    with pytest.raises(RecoveryExactlyOnceError):
        replay_committed_effect_v0(state=state2,idempotency_key_digest=d("idem-a"),operation_digest=d("op-b"))


def test_replay_returns_original_receipt_digest_without_state_change():
    p=permit(); state=make_recovery_effect_state_v0(permit=p)
    intent=prepare_recovery_write_intent_v0(permit=p,state=state,idempotency_key_digest=d("idem-a"))
    receipt,state2=commit_recovery_effect_v0(intent=intent,state=state,effect_evidence_digest=d("effect-a"))
    replay=replay_committed_effect_v0(state=state2,idempotency_key_digest=d("idem-a"),operation_digest=d("op-a"))
    assert replay.replayed is True
    assert replay.receipt_digest==receipt.receipt_digest
    assert state2.next_sequence==2


def test_stale_intent_cannot_commit_after_state_advance():
    p=permit(); state=make_recovery_effect_state_v0(permit=p)
    intent1=prepare_recovery_write_intent_v0(permit=p,state=state,idempotency_key_digest=d("idem-a"))
    _,state2=commit_recovery_effect_v0(intent=intent1,state=state,effect_evidence_digest=d("effect-a"))
    with pytest.raises(RecoveryExactlyOnceError):
        commit_recovery_effect_v0(intent=intent1,state=state2,effect_evidence_digest=d("effect-a"))


def test_epoch_drift_rejected():
    p=permit(epoch=7); state=make_recovery_effect_state_v0(permit=p)
    stale=permit(epoch=8)
    with pytest.raises(RecoveryExactlyOnceError):
        prepare_recovery_write_intent_v0(permit=stale,state=state,idempotency_key_digest=d("idem-a"))
