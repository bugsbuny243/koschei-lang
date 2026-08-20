import hashlib
import pytest

from koschei.library_effect_attestation_quorum_v0 import (
    EffectObservationV0,
    EffectAttestationQuorumError,
    confirm_recovery_effect_v0,
    verify_effect_confirmation_barrier_v0,
)
from koschei.library_recovery_exactly_once_v0 import RecoveryEffectReceiptV0


def d(x:str)->bytes:
    return hashlib.sha3_256(x.encode()).digest()


def receipt()->RecoveryEffectReceiptV0:
    return RecoveryEffectReceiptV0(
        "writer-a",7,d("checkpoint"),3,d("idem"),d("op"),d("effect"),d("intent"),d("receipt"),False,False
    )


def obs(i:str,domain:str,*,rd=None,op=None,ev=None,observed=True):
    r=receipt()
    return EffectObservationV0(
        i,domain,r.receipt_digest if rd is None else rd,
        r.operation_digest if op is None else op,
        r.effect_evidence_digest if ev is None else ev,
        d("state-"+i),observed,False,
    )


def test_two_of_three_independent_domains_confirms():
    r=receipt()
    observations=(obs("a","domain-a"),obs("b","domain-b"),obs("c","domain-c",observed=False))
    b=confirm_recovery_effect_v0(receipt=r,observations=observations,quorum_threshold=2,min_trust_domains=2)
    assert b.confirmed
    assert b.confirming_observer_ids==("a","b")
    assert verify_effect_confirmation_barrier_v0(barrier=b,receipt=r,observations=observations,min_trust_domains=2)


def test_same_trust_domain_cannot_fake_independence():
    r=receipt()
    with pytest.raises(EffectAttestationQuorumError):
        confirm_recovery_effect_v0(
            receipt=r,
            observations=(obs("a","same"),obs("b","same")),
            quorum_threshold=2,
            min_trust_domains=2,
        )


def test_conflicting_observation_fails_closed():
    r=receipt()
    with pytest.raises(EffectAttestationQuorumError):
        confirm_recovery_effect_v0(
            receipt=r,
            observations=(obs("a","x"),obs("b","y",ev=d("different-effect"))),
            quorum_threshold=1,
        )


def test_duplicate_observer_rejected():
    r=receipt()
    with pytest.raises(EffectAttestationQuorumError):
        confirm_recovery_effect_v0(
            receipt=r,
            observations=(obs("a","x"),obs("a","y")),
            quorum_threshold=1,
        )


def test_replayed_receipt_cannot_create_fresh_barrier():
    r=receipt()
    replay=RecoveryEffectReceiptV0(
        r.writer_id,r.epoch,r.checkpoint_digest,r.sequence,r.idempotency_key_digest,
        r.operation_digest,r.effect_evidence_digest,r.intent_digest,r.receipt_digest,True,False
    )
    with pytest.raises(EffectAttestationQuorumError):
        confirm_recovery_effect_v0(receipt=replay,observations=(obs("a","x"),),quorum_threshold=1)


def test_barrier_tamper_detected():
    from dataclasses import replace
    r=receipt(); observations=(obs("a","x"),obs("b","y"))
    b=confirm_recovery_effect_v0(receipt=r,observations=observations,quorum_threshold=2,min_trust_domains=2)
    tampered=replace(b,barrier_digest=d("tampered"))
    assert not verify_effect_confirmation_barrier_v0(barrier=tampered,receipt=r,observations=observations,min_trust_domains=2)
