import hashlib
import pytest

from koschei.library_adversary_learning_resistance_v0 import (
    LearningResistanceDecisionV0, VisibilityPosture,
)
from koschei.library_adaptive_visibility_v0 import (
    VisibilityPolicyV0, AdaptiveVisibilityError,
    derive_adaptive_visibility_v0, derive_compartment_alias_v0,
)


def d(tag:str)->bytes:
    return hashlib.sha3_256(tag.encode()).digest()


def decision(posture=VisibilityPosture.NORMAL, allowed=True, detail=3):
    return LearningResistanceDecisionV0(
        "obs",d("session"),1,10,3,2,0,1,300,posture,detail,d("decision-"+posture.value),allowed,False
    )


def policy():
    return VisibilityPolicyV0(32,8,2,64,12,2,10,True,False)


def test_pressure_shrinks_visibility():
    n=derive_adaptive_visibility_v0(decision=decision(),policy=policy(),current_tick=10,rotation_secret_commitment=d("secret"))
    r=derive_adaptive_visibility_v0(decision=decision(VisibilityPosture.REDUCED,True,2),policy=policy(),current_tick=10,rotation_secret_commitment=d("secret"))
    m=derive_adaptive_visibility_v0(decision=decision(VisibilityPosture.MINIMAL,True,1),policy=policy(),current_tick=10,rotation_secret_commitment=d("secret"))
    assert (n.root_budget,r.root_budget,m.root_budget)==(32,8,2)
    assert (n.relation_budget,r.relation_budget,m.relation_budget)==(64,12,2)


def test_contained_has_zero_surface():
    e=derive_adaptive_visibility_v0(decision=decision(VisibilityPosture.CONTAINED,False,0),policy=policy(),current_tick=10,rotation_secret_commitment=d("secret"))
    assert not e.allowed and e.root_budget==0 and e.relation_budget==0 and e.diagnostic_detail_ceiling==0


def test_alias_rotates_across_epochs():
    a=derive_adaptive_visibility_v0(decision=decision(),policy=policy(),current_tick=10,rotation_secret_commitment=d("secret"))
    b=derive_adaptive_visibility_v0(decision=decision(),policy=policy(),current_tick=20,rotation_secret_commitment=d("secret"))
    assert a.visibility_epoch!=b.visibility_epoch
    assert derive_compartment_alias_v0(envelope=a,canonical_subject_digest=d("root"),ordinal=0)!=derive_compartment_alias_v0(envelope=b,canonical_subject_digest=d("root"),ordinal=0)


def test_same_inputs_are_deterministic():
    a=derive_adaptive_visibility_v0(decision=decision(),policy=policy(),current_tick=10,rotation_secret_commitment=d("secret"))
    b=derive_adaptive_visibility_v0(decision=decision(),policy=policy(),current_tick=10,rotation_secret_commitment=d("secret"))
    assert a==b


def test_alias_rejected_for_contained_envelope():
    e=derive_adaptive_visibility_v0(decision=decision(VisibilityPosture.CONTAINED,False,0),policy=policy(),current_tick=10,rotation_secret_commitment=d("secret"))
    with pytest.raises(AdaptiveVisibilityError):
        derive_compartment_alias_v0(envelope=e,canonical_subject_digest=d("root"),ordinal=0)


def test_policy_must_shrink_monotonically():
    bad=VisibilityPolicyV0(4,8,2,64,12,2,10,True,False)
    with pytest.raises(AdaptiveVisibilityError):
        derive_adaptive_visibility_v0(decision=decision(),policy=bad,current_tick=10,rotation_secret_commitment=d("secret"))
