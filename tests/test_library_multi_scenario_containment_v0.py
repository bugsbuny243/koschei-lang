from koschei.library_multi_scenario_containment_v0 import (
    MultiScenarioContainmentError,
    combine_containment_scenarios_v0,
)
from koschei.library_containment_optimizer_v0 import ContainmentRecommendationV0
from koschei.library_trust_graph_v0 import (
    LibraryTrustGraphV0,
    TrustGraphNodeV0,
    build_library_trust_graph_v0,
)

D=lambda b: bytes([b])*32


def graph():
    return build_library_trust_graph_v0(nodes=(
        TrustGraphNodeV0("ka",1,D(1),D(11)),
        TrustGraphNodeV0("vor",1,D(2),D(12)),
        TrustGraphNodeV0("nur",1,D(3),D(13)),
    ))


def rec(g, tag, isolated, preserved, feasible=True, cuts=()):
    return ContainmentRecommendationV0(
        g.graph_digest,D(tag),tuple(cuts),tuple(preserved),tuple(isolated),
        len(preserved),len(isolated),D(tag+20),feasible,False,
    )


def test_unions_isolation_and_intersects_preservation():
    g=graph()
    a=rec(g,1,("ka",),("vor","nur"),cuts=(("ka","vor"),))
    b=rec(g,2,("vor",),("ka","nur"),cuts=(("vor","nur"),))
    out=combine_containment_scenarios_v0(graph=g,scenarios=(a,b))
    assert out.feasible
    assert out.isolated_roots==("ka","vor")
    assert out.preserved_roots==("nur",)
    assert set(out.cut_edges)=={("ka","vor"),("vor","nur")}


def test_order_independent_digest():
    g=graph(); a=rec(g,1,("ka",),("vor","nur")); b=rec(g,2,("vor",),("ka","nur"))
    x=combine_containment_scenarios_v0(graph=g,scenarios=(a,b))
    y=combine_containment_scenarios_v0(graph=g,scenarios=(b,a))
    assert x.combined_digest==y.combined_digest


def test_any_infeasible_scenario_denies_preservation():
    g=graph(); a=rec(g,1,("ka",),("vor","nur")); b=rec(g,2,("vor",),("ka","nur"),False)
    out=combine_containment_scenarios_v0(graph=g,scenarios=(a,b))
    assert not out.feasible
    assert out.preserved_roots==()


def test_duplicate_scenario_rejected():
    g=graph(); a=rec(g,1,("ka",),("vor","nur"))
    try:
        combine_containment_scenarios_v0(graph=g,scenarios=(a,a))
    except MultiScenarioContainmentError:
        pass
    else:
        raise AssertionError("duplicate scenario accepted")


def test_graph_drift_rejected():
    g=graph()
    other=build_library_trust_graph_v0(nodes=(TrustGraphNodeV0("x",1,D(9),D(19)),))
    a=rec(other,1,("x",),())
    try:
        combine_containment_scenarios_v0(graph=g,scenarios=(a,))
    except MultiScenarioContainmentError:
        pass
    else:
        raise AssertionError("graph drift accepted")
