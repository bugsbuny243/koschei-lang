import hashlib
import pytest

from koschei.library_compromise_recovery_v0 import (
    CompromiseClass,
    CompromiseRecoveryError,
    CompromiseSignalV0,
    close_recovery_v0,
    derive_recovery_plan_v0,
)
from koschei.library_trust_graph_v0 import (
    LibraryTrustGraphV0,
    TrustGraphEdgeV0,
    TrustGraphNodeV0,
    build_library_trust_graph_v0,
)


def d(tag:str)->bytes:
    return hashlib.sha3_256(tag.encode()).digest()


def graph(gen_a=1, gen_b=1, tech_a="ta", tech_b="tb"):
    a=TrustGraphNodeV0("ka",gen_a,d("bind-a"+str(gen_a)),d(tech_a))
    b=TrustGraphNodeV0("vor",gen_b,d("bind-b"+str(gen_b)),d(tech_b))
    e=TrustGraphEdgeV0("ka","vor",d("rel"),d("edge"))
    return build_library_trust_graph_v0(nodes=(a,b),edges=(e,))


def test_compromised_root_quarantines_touching_edges_and_revokes_generation():
    g=graph()
    s=CompromiseSignalV0("ka",1,CompromiseClass.KEY,d("signal"),7)
    plan=derive_recovery_plan_v0(graph=g,signals=(s,),detected_epoch=7)
    assert plan.quarantined_roots==("ka",)
    assert plan.revoked_generations==(("ka",1),)
    assert plan.disabled_edges==(("ka","vor"),)
    assert d("signal") in plan.required_evidence
    assert d("edge") in plan.required_evidence


def test_unknown_root_and_generation_drift_fail_closed():
    g=graph()
    with pytest.raises(CompromiseRecoveryError):
        derive_recovery_plan_v0(graph=g,signals=(CompromiseSignalV0("x",1,CompromiseClass.ROOT,d("e"),2),),detected_epoch=2)
    with pytest.raises(CompromiseRecoveryError):
        derive_recovery_plan_v0(graph=g,signals=(CompromiseSignalV0("ka",2,CompromiseClass.ROOT,d("e"),2),),detected_epoch=2)


def test_empty_evidence_rejected():
    g=graph()
    with pytest.raises(CompromiseRecoveryError):
        derive_recovery_plan_v0(graph=g,signals=(CompromiseSignalV0("ka",1,CompromiseClass.KEY,b"\x00"*32,2),),detected_epoch=2)


def test_recovery_cannot_close_on_same_graph_or_same_generation():
    g=graph()
    plan=derive_recovery_plan_v0(graph=g,signals=(CompromiseSignalV0("ka",1,CompromiseClass.KEY,d("e"),3),),detected_epoch=3)
    with pytest.raises(CompromiseRecoveryError):
        close_recovery_v0(plan=plan,replacement_graph=g,closure_epoch=4,evidence_digest=d("close"))
    # Graph differs only by unrelated technology; compromised ka generation is still 1.
    bad=graph(gen_a=1,gen_b=1,tech_b="tb2")
    with pytest.raises(CompromiseRecoveryError):
        close_recovery_v0(plan=plan,replacement_graph=bad,closure_epoch=4,evidence_digest=d("close"))


def test_recovery_closes_after_generation_advance():
    g=graph()
    plan=derive_recovery_plan_v0(graph=g,signals=(CompromiseSignalV0("ka",1,CompromiseClass.KEY,d("e"),3),),detected_epoch=3)
    replacement=graph(gen_a=2)
    receipt=close_recovery_v0(plan=plan,replacement_graph=replacement,closure_epoch=4,evidence_digest=d("close"))
    assert receipt.closed is True
    assert receipt.replacement_graph_digest==replacement.graph_digest
