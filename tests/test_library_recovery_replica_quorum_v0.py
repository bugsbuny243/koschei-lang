import hashlib
import pytest

from koschei.library_recovery_transaction_v0 import RecoveryTransactionV0, RecoveryTransactionState
from koschei.library_recovery_journal_v0 import open_recovery_journal_v0, append_recovery_step_v0
from koschei.library_recovery_replica_quorum_v0 import (
    RecoveryJournalReplicaV0,
    RecoveryReplicaQuorumError,
    derive_recovery_checkpoint_v0,
    verify_recovery_checkpoint_v0,
)


def d(label:str)->bytes:
    return hashlib.sha3_256(label.encode()).digest()


def tx():
    return RecoveryTransactionV0(d("g"),d("p"),("s1","s2"),("s1","s2"),d("prep"),RecoveryTransactionState.PREPARED,False)


def journal0(t):
    return open_recovery_journal_v0(transaction=t,evidence_digest=d("open"))


def journal1(t):
    return append_recovery_step_v0(journal=journal0(t),transaction=t,step_id="s1",evidence_digest=d("s1"))


def replica(rid,j,durable=True):
    return RecoveryJournalReplicaV0(rid,j,d("store-"+rid),durable,False)


def test_two_of_three_quorum_checkpoint():
    t=tx(); j=journal1(t)
    cp=derive_recovery_checkpoint_v0(transaction=t,replicas=(replica("a",j),replica("b",j),replica("c",journal0(t))),quorum_threshold=2)
    assert cp.canonical_sequence==2
    assert cp.agreeing_replica_ids==("a","b")
    assert cp.divergent_replica_ids==("c",)
    assert verify_recovery_checkpoint_v0(checkpoint=cp,transaction=t,replicas=(replica("a",j),replica("b",j),replica("c",journal0(t))))


def test_no_quorum_fails_closed():
    t=tx()
    with pytest.raises(RecoveryReplicaQuorumError):
        derive_recovery_checkpoint_v0(transaction=t,replicas=(replica("a",journal1(t)),replica("b",journal0(t))),quorum_threshold=2)


def test_duplicate_replica_identity_rejected():
    t=tx(); j=journal1(t)
    with pytest.raises(RecoveryReplicaQuorumError):
        derive_recovery_checkpoint_v0(transaction=t,replicas=(replica("a",j),replica("a",j)),quorum_threshold=2)


def test_non_durable_replica_cannot_form_quorum():
    t=tx(); j=journal1(t)
    with pytest.raises(RecoveryReplicaQuorumError):
        derive_recovery_checkpoint_v0(transaction=t,replicas=(replica("a",j,False),replica("b",j,False)),quorum_threshold=2)


def test_durable_ahead_of_selected_quorum_fails_closed():
    t=tx(); j0=journal0(t); j1=journal1(t)
    # two replicas agree at sequence 1, but a durable peer is ahead at sequence 2.
    with pytest.raises(RecoveryReplicaQuorumError):
        derive_recovery_checkpoint_v0(transaction=t,replicas=(replica("a",j0),replica("b",j0),replica("c",j1)),quorum_threshold=2)


def test_tampered_checkpoint_verification_fails():
    t=tx(); j=journal1(t); reps=(replica("a",j),replica("b",j))
    cp=derive_recovery_checkpoint_v0(transaction=t,replicas=reps,quorum_threshold=2)
    bad=type(cp)(cp.graph_digest,cp.recovery_plan_digest,cp.preparation_digest,d("wrong"),cp.canonical_sequence,cp.agreeing_replica_ids,cp.divergent_replica_ids,cp.quorum_threshold,cp.checkpoint_digest,cp.durable,cp.split_brain,cp.authority)
    assert not verify_recovery_checkpoint_v0(checkpoint=bad,transaction=t,replicas=reps)
