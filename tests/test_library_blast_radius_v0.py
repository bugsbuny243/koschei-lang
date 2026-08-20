import hashlib
import pytest

from koschei.library_trust_graph_v0 import (
    TrustGraphNodeV0, TrustGraphEdgeV0, build_library_trust_graph_v0,
)
from koschei.library_compromise_recovery_v0 import (
    CompromiseClass, CompromiseSignalV0, derive_recovery_plan_v0,
)
from koschei.library_blast_radius_v0 import BlastRadiusError, derive_blast_radius_v0


def d(x:str)->bytes:
    return hashlib.sha3_256(x.encode()).digest()


def graph():
    nodes=tuple(TrustGraphNodeV0(r,1,d(r+"b"),d(r+"t")) for r in ("ka","vor","nur","thal"))
    edges=(
        TrustGraphEdgeV0("ka","vor",d("r1"),d("e1")),
        TrustGraphEdgeV0("vor","nur",d("r2"),d("e2")),
        TrustGraphEdgeV0("thal","nur",d("r3"),d("e3")),
    )
    return build_library_trust_graph_v0(nodes=nodes,edges=edges)


def plan(g):
    return derive_recovery_plan_v0(
        graph=g,
        signals=(CompromiseSignalV0("ka",1,CompromiseClass.ROOT,d("bad"),7),),
        detected_epoch=7,
    )


def test_zero_hops_contains_only_compromised_root_and_cuts_boundary():
    g=graph(); p=plan(g)
    r=derive_blast_radius_v0(graph=g,plan=p,max_hops=0)
    assert r.affected_roots==("ka",)
    assert r.boundary_cut_edges==(("ka","vor"),)
    assert set(r.safe_roots)=={"vor","nur","thal"}


def test_one_hop_expands_and_moves_cut_boundary():
    g=graph(); p=plan(g)
    r=derive_blast_radius_v0(graph=g,plan=p,max_hops=1)
    assert set(r.affected_roots)=={"ka","vor"}
    assert r.boundary_cut_edges==(("vor","nur"),)


def test_unbounded_reaches_connected_component():
    g=graph(); p=plan(g)
    r=derive_blast_radius_v0(graph=g,plan=p,max_hops=None)
    assert set(r.affected_roots)=={"ka","vor","nur","thal"}
    assert r.boundary_cut_edges==()
    assert r.safe_roots==()


def test_plan_graph_drift_fails_closed():
    g=graph(); p=plan(g)
    g2=build_library_trust_graph_v0(
        nodes=g.nodes,
        edges=g.edges+(TrustGraphEdgeV0("ka","nur",d("r4"),d("e4")),),
    )
    with pytest.raises(BlastRadiusError):
        derive_blast_radius_v0(graph=g2,plan=p,max_hops=1)


def test_invalid_hop_budget_fails_closed():
    g=graph(); p=plan(g)
    with pytest.raises(BlastRadiusError):
        derive_blast_radius_v0(graph=g,plan=p,max_hops=-1)


def test_digest_is_deterministic():
    g=graph(); p=plan(g)
    a=derive_blast_radius_v0(graph=g,plan=p,max_hops=1)
    b=derive_blast_radius_v0(graph=g,plan=p,max_hops=1)
    assert a.radius_digest==b.radius_digest
