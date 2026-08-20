import hashlib
import pytest

from koschei.library_trust_graph_v0 import TrustGraphNodeV0, build_library_trust_graph_v0
from koschei.library_multi_scenario_containment_v0 import MultiScenarioContainmentV0
from koschei.library_policy_conflict_resolution_v0 import (
    PolicyConflictResolutionError,
    RecoveryPriority,
    RecoveryStepV0,
    RecoveryDependencyV0,
    resolve_recovery_priorities_v0,
)


def d(x:bytes)->bytes:
    return hashlib.sha3_256(x).digest()


def graph():
    nodes=(
        TrustGraphNodeV0("ka",1,d(b"ka-r"),d(b"ka-t")),
        TrustGraphNodeV0("vor",1,d(b"vor-r"),d(b"vor-t")),
        TrustGraphNodeV0("nur",1,d(b"nur-r"),d(b"nur-t")),
    )
    return build_library_trust_graph_v0(nodes=nodes)


def containment(g, *, feasible=True):
    return MultiScenarioContainmentV0(
        g.graph_digest,
        (d(b"scenario"),),
        ("ka",),
        ("nur","vor") if feasible else (),
        (),
        d(b"combined"),
        feasible,
        False,
    )


def steps():
    return (
        RecoveryStepV0("rotate-ka","ka",d(b"rotate"),d(b"e1"),RecoveryPriority.CRITICAL,False),
        RecoveryStepV0("rebuild-ka","ka",d(b"rebuild"),d(b"e2"),RecoveryPriority.HIGH,True),
        RecoveryStepV0("audit-vor","vor",d(b"audit"),d(b"e3"),RecoveryPriority.LOW,False),
    )


def test_dependency_and_priority_order_are_canonical():
    g=graph(); c=containment(g)
    deps=(RecoveryDependencyV0("rotate-ka","rebuild-ka",d(b"dep")),)
    p=resolve_recovery_priorities_v0(graph=g,containment=c,steps=steps(),dependencies=deps)
    assert p.executable is True
    assert p.ordered_step_ids == ("rotate-ka","rebuild-ka","audit-vor")
    assert p.deferred_step_ids == ("audit-vor",)


def test_input_order_does_not_change_plan_digest():
    g=graph(); c=containment(g)
    deps=(RecoveryDependencyV0("rotate-ka","rebuild-ka",d(b"dep")),)
    p1=resolve_recovery_priorities_v0(graph=g,containment=c,steps=steps(),dependencies=deps)
    p2=resolve_recovery_priorities_v0(graph=g,containment=c,steps=tuple(reversed(steps())),dependencies=deps)
    assert p1.plan_digest == p2.plan_digest
    assert p1.ordered_step_ids == p2.ordered_step_ids


def test_cycle_fails_closed():
    g=graph(); c=containment(g)
    deps=(
        RecoveryDependencyV0("rotate-ka","rebuild-ka",d(b"a")),
        RecoveryDependencyV0("rebuild-ka","rotate-ka",d(b"b")),
    )
    with pytest.raises(PolicyConflictResolutionError,match="cyclic"):
        resolve_recovery_priorities_v0(graph=g,containment=c,steps=steps(),dependencies=deps)


def test_infeasible_containment_cannot_recover():
    g=graph(); c=containment(g,feasible=False)
    with pytest.raises(PolicyConflictResolutionError,match="infeasible"):
        resolve_recovery_priorities_v0(graph=g,containment=c,steps=steps())


def test_empty_evidence_fails_closed():
    g=graph(); c=containment(g)
    bad=(RecoveryStepV0("x","ka",d(b"x"),b"\x00"*32,RecoveryPriority.HIGH),)
    with pytest.raises(PolicyConflictResolutionError,match="evidence"):
        resolve_recovery_priorities_v0(graph=g,containment=c,steps=bad)


def test_duplicate_action_same_root_is_rejected():
    g=graph(); c=containment(g)
    dup=(
        RecoveryStepV0("a","ka",d(b"same"),d(b"1"),RecoveryPriority.HIGH),
        RecoveryStepV0("b","ka",d(b"same"),d(b"2"),RecoveryPriority.NORMAL),
    )
    with pytest.raises(PolicyConflictResolutionError,match="duplicate recovery action"):
        resolve_recovery_priorities_v0(graph=g,containment=c,steps=dup)
