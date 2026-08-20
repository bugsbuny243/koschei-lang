import hashlib
import pytest

from koschei.library_adversary_learning_resistance_v0 import (
    LearningResistanceDecisionV0, VisibilityPosture,
)
from koschei.library_cross_session_continuity_v0 import (
    ContinuityPolicyV0, CrossSessionContinuityError,
    derive_continuity_token_v0, aggregate_cross_session_learning_v0,
)

D=lambda s: hashlib.sha3_256(s.encode()).digest()


def dec(name,units,targets,bounds,posture=VisibilityPosture.NORMAL,allowed=True):
    return LearningResistanceDecisionV0(
        "observer",D("session-"+name),0,10,units,targets,bounds,1,100,
        posture,3,D("decision-"+name),allowed,False,
    )


def policy():
    return ContinuityPolicyV0(100,3,30,12,4,False)


def test_token_rotates_by_epoch_but_is_stable_inside_epoch():
    p=policy()
    a=derive_continuity_token_v0(anchor_commitment=D("anchor"),current_tick=10,policy=p,rotation_secret_commitment=D("secret"))
    b=derive_continuity_token_v0(anchor_commitment=D("anchor"),current_tick=90,policy=p,rotation_secret_commitment=D("secret"))
    c=derive_continuity_token_v0(anchor_commitment=D("anchor"),current_tick=100,policy=p,rotation_secret_commitment=D("secret"))
    assert a.token_digest==b.token_digest
    assert a.token_digest!=c.token_digest


def test_cross_session_budget_accumulates_and_can_contain():
    p=policy(); t=derive_continuity_token_v0(anchor_commitment=D("anchor"),current_tick=10,policy=p,rotation_secret_commitment=D("secret"))
    out=aggregate_cross_session_learning_v0(token=t,decisions=(dec("a",10,4,1),dec("b",12,5,2),dec("c",10,4,2)),policy=p)
    assert out.posture is VisibilityPosture.CONTAINED
    assert not out.allowed


def test_never_relaxes_worst_session_posture():
    p=policy(); t=derive_continuity_token_v0(anchor_commitment=D("anchor"),current_tick=10,policy=p,rotation_secret_commitment=D("secret"))
    out=aggregate_cross_session_learning_v0(token=t,decisions=(dec("a",5,2,0),dec("b",5,2,0,VisibilityPosture.MINIMAL,True)),policy=p)
    assert out.posture is VisibilityPosture.MINIMAL
    assert out.allowed


def test_duplicate_session_rejected():
    p=policy(); t=derive_continuity_token_v0(anchor_commitment=D("anchor"),current_tick=10,policy=p,rotation_secret_commitment=D("secret")); d=dec("a",1,1,0)
    with pytest.raises(CrossSessionContinuityError):
        aggregate_cross_session_learning_v0(token=t,decisions=(d,d),policy=p)


def test_session_count_budget_cannot_be_reset_by_new_sessions():
    p=ContinuityPolicyV0(100,2,100,100,100,False)
    t=derive_continuity_token_v0(anchor_commitment=D("anchor"),current_tick=10,policy=p,rotation_secret_commitment=D("secret"))
    out=aggregate_cross_session_learning_v0(token=t,decisions=(dec("a",1,1,0),dec("b",1,1,0),dec("c",1,1,0)),policy=p)
    assert out.posture is VisibilityPosture.CONTAINED


def test_order_independent_digest():
    p=policy(); t=derive_continuity_token_v0(anchor_commitment=D("anchor"),current_tick=10,policy=p,rotation_secret_commitment=D("secret")); a=dec("a",3,2,1); b=dec("b",4,1,0)
    x=aggregate_cross_session_learning_v0(token=t,decisions=(a,b),policy=p)
    y=aggregate_cross_session_learning_v0(token=t,decisions=(b,a),policy=p)
    assert x.decision_digest==y.decision_digest
