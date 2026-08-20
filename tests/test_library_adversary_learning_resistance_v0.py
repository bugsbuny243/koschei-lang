import hashlib
import pytest

from koschei.library_adversary_learning_resistance_v0 import (
    AdversaryLearningResistanceError,
    DiscoveryClass,
    DiscoveryObservationV0,
    KnowledgeBudgetV0,
    VisibilityPosture,
    evaluate_learning_resistance_v0,
)


def d(label:str)->bytes:
    return hashlib.sha3_256(label.encode()).digest()


def obs(*,tick:int,cls:DiscoveryClass,target:str,units:int,boundary:bool=False,evidence:str|None=None):
    return DiscoveryObservationV0(
        observer_id="observer-a",
        session_digest=d("session-a"),
        tick=tick,
        discovery_class=cls,
        target_digest=d(target),
        novelty_units=units,
        boundary_attempt=boundary,
        evidence_digest=d(evidence or f"e-{tick}-{target}"),
    )


def budget(**kw):
    base=dict(
        max_total_units=100,
        max_distinct_targets=10,
        max_boundary_attempts=4,
        max_classes=5,
        window_ticks=20,
        reduced_ratio_per_mille=600,
        minimal_ratio_per_mille=850,
    )
    base.update(kw)
    return KnowledgeBudgetV0(**base)


def test_normal_posture_for_low_discovery_pressure():
    result=evaluate_learning_resistance_v0(
        observations=(obs(tick=10,cls=DiscoveryClass.ROOT_ENUMERATION,target="a",units=10),),
        budget=budget(),current_tick=10,
    )
    assert result.posture is VisibilityPosture.NORMAL
    assert result.allowed is True
    assert result.exposed_detail_ceiling==3


def test_reduced_then_minimal_posture_as_budget_is_consumed():
    reduced=evaluate_learning_resistance_v0(
        observations=(obs(tick=10,cls=DiscoveryClass.ROOT_ENUMERATION,target="a",units=60),),
        budget=budget(),current_tick=10,
    )
    assert reduced.posture is VisibilityPosture.REDUCED

    minimal=evaluate_learning_resistance_v0(
        observations=(obs(tick=10,cls=DiscoveryClass.ROOT_ENUMERATION,target="a",units=85),),
        budget=budget(),current_tick=10,
    )
    assert minimal.posture is VisibilityPosture.MINIMAL
    assert minimal.exposed_detail_ceiling==1


def test_budget_excess_contains_without_counterattack():
    result=evaluate_learning_resistance_v0(
        observations=(
            obs(tick=10,cls=DiscoveryClass.AUTHORITY_PROBING,target="a",units=60,boundary=True),
            obs(tick=11,cls=DiscoveryClass.RELATION_MAPPING,target="b",units=50,boundary=True),
        ),
        budget=budget(),current_tick=11,
    )
    assert result.posture is VisibilityPosture.CONTAINED
    assert result.allowed is False
    assert result.exposed_detail_ceiling==0


def test_boundary_attempt_budget_can_trigger_containment_independently():
    observations=tuple(
        obs(tick=10+i,cls=DiscoveryClass.AUTHORITY_PROBING,target=f"t{i}",units=1,boundary=True)
        for i in range(5)
    )
    result=evaluate_learning_resistance_v0(
        observations=observations,budget=budget(),current_tick=14,
    )
    assert result.boundary_attempts==5
    assert result.posture is VisibilityPosture.CONTAINED


def test_window_expires_old_discovery_pressure():
    result=evaluate_learning_resistance_v0(
        observations=(
            obs(tick=1,cls=DiscoveryClass.AUTHORITY_PROBING,target="old",units=100,boundary=True),
            obs(tick=30,cls=DiscoveryClass.ROOT_ENUMERATION,target="fresh",units=5),
        ),
        budget=budget(window_ticks=10),current_tick=30,
    )
    assert result.total_units==5
    assert result.posture is VisibilityPosture.NORMAL


def test_mixed_session_is_rejected():
    good=obs(tick=10,cls=DiscoveryClass.ROOT_ENUMERATION,target="a",units=1)
    bad=DiscoveryObservationV0(
        observer_id="observer-a",session_digest=d("session-b"),tick=11,
        discovery_class=DiscoveryClass.ROOT_ENUMERATION,target_digest=d("b"),
        novelty_units=1,evidence_digest=d("e-b"),
    )
    with pytest.raises(AdversaryLearningResistanceError):
        evaluate_learning_resistance_v0(observations=(good,bad),budget=budget(),current_tick=11)


def test_duplicate_observation_is_rejected():
    x=obs(tick=10,cls=DiscoveryClass.ERROR_ORACLE,target="a",units=1,evidence="same")
    with pytest.raises(AdversaryLearningResistanceError):
        evaluate_learning_resistance_v0(observations=(x,x),budget=budget(),current_tick=10)


def test_decision_digest_is_input_order_independent():
    a=obs(tick=10,cls=DiscoveryClass.ROOT_ENUMERATION,target="a",units=10)
    b=obs(tick=11,cls=DiscoveryClass.RELATION_MAPPING,target="b",units=20)
    x=evaluate_learning_resistance_v0(observations=(a,b),budget=budget(),current_tick=11)
    y=evaluate_learning_resistance_v0(observations=(b,a),budget=budget(),current_tick=11)
    assert x.decision_digest==y.decision_digest
