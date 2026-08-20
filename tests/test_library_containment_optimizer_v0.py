import hashlib
import pytest

from koschei.library_trust_graph_v0 import TrustGraphNodeV0, TrustGraphEdgeV0, build_library_trust_graph_v0
from koschei.library_blast_radius_v0 import BlastRadiusV0
from koschei.library_containment_optimizer_v0 import (
    ContainmentOptimizerError, RootServiceWeightV0, ContainmentPolicyV0,
    optimize_containment_v0,
)


def d(x:str)->bytes:
    return hashlib.sha3_256(x.encode()).digest()


def graph():
    nodes=(
        TrustGraphNodeV0("ka",1,d("ka-r"),d("ka-t")),
        TrustGraphNodeV0("vor",1,d("vor-r"),d("vor-t")),
        TrustGraphNodeV0("nur",1,d("nur-r"),d("nur-t")),
    )
    edges=(
        TrustGraphEdgeV0("ka","vor",d("r1"),d("e1")),
        TrustGraphEdgeV0("vor","nur",d("r2"),d("e2")),
    )
    return build_library_trust_graph_v0(nodes=nodes,edges=edges)


def radius(g):
    return BlastRadiusV0(
        g.graph_digest,d("plan"),("ka",),("ka","vor"),(('ka','vor'),),(('vor','nur'),),("nur",),d("radius"),False
    )


def weights():
    return (
        RootServiceWeightV0("ka",10,3),
        RootServiceWeightV0("vor",20,4),
        RootServiceWeightV0("nur",100,1),
    )


def test_preserves_safe_side_when_budget_allows():
    g=graph(); r=radius(g)
    out=optimize_containment_v0(graph=g,radius=r,weights=weights(),policy=ContainmentPolicyV0(7))
    assert out.feasible is True
    assert out.isolated_roots==("ka","vor")
    assert out.preserved_roots==("nur",)
    assert out.cut_edges==(("vor","nur"),)
    assert out.preserved_service_value==100
    assert out.disruption_cost==7


def test_budget_failure_does_not_weaken_containment():
    g=graph(); r=radius(g)
    out=optimize_containment_v0(graph=g,radius=r,weights=weights(),policy=ContainmentPolicyV0(6))
    assert out.feasible is False
    assert out.isolated_roots==("ka","vor")
    assert out.preserved_roots==()
    assert out.cut_edges==(("vor","nur"),)


def test_requires_weight_for_every_root():
    g=graph(); r=radius(g)
    with pytest.raises(ContainmentOptimizerError):
        optimize_containment_v0(graph=g,radius=r,weights=weights()[:-1],policy=ContainmentPolicyV0(7))


def test_graph_drift_fails_closed():
    g=graph(); r=radius(g)
    bad=BlastRadiusV0(d("other"),r.recovery_plan_digest,r.compromised_roots,r.affected_roots,r.internal_edges,r.boundary_cut_edges,r.safe_roots,r.radius_digest,False)
    with pytest.raises(ContainmentOptimizerError):
        optimize_containment_v0(graph=g,radius=bad,weights=weights(),policy=ContainmentPolicyV0(7))


def test_weight_order_is_canonical():
    g=graph(); r=radius(g)
    a=optimize_containment_v0(graph=g,radius=r,weights=weights(),policy=ContainmentPolicyV0(7))
    b=optimize_containment_v0(graph=g,radius=r,weights=tuple(reversed(weights())),policy=ContainmentPolicyV0(7))
    assert a.recommendation_digest==b.recommendation_digest
