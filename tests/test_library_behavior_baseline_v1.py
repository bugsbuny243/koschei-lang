import pytest

from koschei.library_boundary_v1 import (
    make_resource_budget_v1,
    observe_library_effect_v1,
)
from koschei.library_behavior_baseline_v1 import (
    LibraryBehaviorBaselineError,
    assess_library_behavior_v1,
    derive_library_behavior_baseline_v1,
)

ART = b"a" * 32
REV = b"r" * 32
T1 = b"1" * 32
T2 = b"2" * 32


def obs(effect, *, cpu=10, mem=20, inp=30, nesting=1, target=None, artifact=ART):
    return observe_library_effect_v1(
        artifact_digest=artifact, effect=effect, cpu_units=cpu,
        memory_bytes=mem, input_bytes=inp, nesting=nesting,
        target_digest=target,
    )


def budget():
    return make_resource_budget_v1(cpu_units=1000, memory_bytes=1000,
        input_bytes=1000, nesting=100)


def baseline():
    return derive_library_behavior_baseline_v1(
        artifact_digest=ART, revision_digest=REV, epoch=4,
        observations=(obs("decode", cpu=10), obs("compute", cpu=20),
                      obs("network", cpu=5, target=T1)),
        hard_budget=budget(),
    )


def test_normal_behavior_conforms_without_granting_any_authority():
    b = baseline()
    result = assess_library_behavior_v1(b, obs("compute", cpu=19))
    assert result.conforming is True
    assert result.delta is None
    assert not hasattr(b, "grant")
    assert not hasattr(b, "execute")


def test_new_effect_is_predictive_authority_delta_not_auto_learning():
    b = baseline()
    result = assess_library_behavior_v1(b, obs("secret", target=T1))
    assert result.conforming is False
    assert result.delta.kind == "new-effect"
    assert result.precursor.reason == "behavior-new-effect"
    assert "secret" not in {e.effect for e in b.effects}


def test_target_expansion_is_detected_before_it_becomes_normal():
    b = baseline()
    result = assess_library_behavior_v1(b, obs("network", target=T2))
    assert result.delta.kind == "target-expansion"


def test_resource_drift_is_security_evidence():
    b = baseline()
    assert assess_library_behavior_v1(b, obs("compute", cpu=21)).delta.kind == "cpu-drift"
    assert assess_library_behavior_v1(b, obs("decode", mem=21)).delta.kind == "memory-drift"
    assert assess_library_behavior_v1(b, obs("decode", inp=31)).delta.kind == "input-drift"
    assert assess_library_behavior_v1(b, obs("decode", nesting=2)).delta.kind == "nesting-drift"


def test_artifact_identity_drift_is_detected():
    b = baseline()
    result = assess_library_behavior_v1(b, obs("compute", artifact=b"x" * 32))
    assert result.delta.kind == "artifact-identity-drift"


def test_baseline_is_deterministic_and_order_independent():
    rows = (obs("decode"), obs("compute", cpu=20), obs("network", target=T1))
    a = derive_library_behavior_baseline_v1(
        artifact_digest=ART, revision_digest=REV, epoch=1,
        observations=rows, hard_budget=budget())
    b = derive_library_behavior_baseline_v1(
        artifact_digest=ART, revision_digest=REV, epoch=1,
        observations=tuple(reversed(rows)), hard_budget=budget())
    assert a.baseline_digest == b.baseline_digest


def test_baseline_cannot_normalize_already_overbudget_behavior():
    with pytest.raises(LibraryBehaviorBaselineError):
        derive_library_behavior_baseline_v1(
            artifact_digest=ART, revision_digest=REV, epoch=1,
            observations=(obs("compute", cpu=1001),), hard_budget=budget())


def test_mixed_artifact_training_is_rejected():
    with pytest.raises(LibraryBehaviorBaselineError):
        derive_library_behavior_baseline_v1(
            artifact_digest=ART, revision_digest=REV, epoch=1,
            observations=(obs("compute"), obs("compute", artifact=b"x" * 32)),
            hard_budget=budget())
