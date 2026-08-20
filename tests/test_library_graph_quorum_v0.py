import hashlib
import pytest

from koschei.library_graph_quorum_v0 import (
    GraphQuorumError,
    QuorumPolicyV0,
    RootAttestationV0,
    evaluate_graph_quorum_v0,
)
from koschei.library_trust_graph_v0 import (
    LibraryTrustGraphV0,
    TrustGraphEdgeV0,
    TrustGraphNodeV0,
    build_library_trust_graph_v0,
)


def d(label: str) -> bytes:
    return hashlib.sha3_256(label.encode()).digest()


def graph() -> LibraryTrustGraphV0:
    a=TrustGraphNodeV0("ka",1,d("ka-bind"),d("tech-a"))
    b=TrustGraphNodeV0("vor",1,d("vor-bind"),d("tech-b"))
    e=TrustGraphEdgeV0("ka","vor",d("relation"),d("edge-evidence"))
    return build_library_trust_graph_v0(nodes=(a,b),edges=(e,))


def att(g, root, tech, accepted=True, generation=1):
    return RootAttestationV0(root,generation,g.graph_digest,d(root+"-evidence"),tech,accepted,False)


def test_quorum_requires_threshold():
    g=graph(); p=QuorumPolicyV0(2)
    a=att(g,"ka",d("tech-a"))
    assert not evaluate_graph_quorum_v0(graph=g,policy=p,attestations=(a,)).active
    b=att(g,"vor",d("tech-b"))
    decision=evaluate_graph_quorum_v0(graph=g,policy=p,attestations=(a,b))
    assert decision.active
    assert decision.accepted_roots==("ka","vor")


def test_duplicate_and_unknown_attestations_fail_closed():
    g=graph(); p=QuorumPolicyV0(1)
    a=att(g,"ka",d("tech-a"))
    with pytest.raises(GraphQuorumError):
        evaluate_graph_quorum_v0(graph=g,policy=p,attestations=(a,a))
    x=RootAttestationV0("ghost",1,g.graph_digest,d("x"),d("x-tech"),True)
    with pytest.raises(GraphQuorumError):
        evaluate_graph_quorum_v0(graph=g,policy=p,attestations=(x,))


def test_generation_graph_and_technology_drift_fail_closed():
    g=graph(); p=QuorumPolicyV0(1)
    with pytest.raises(GraphQuorumError):
        evaluate_graph_quorum_v0(graph=g,policy=p,attestations=(att(g,"ka",d("tech-a"),generation=2),))
    wrong_graph=RootAttestationV0("ka",1,d("other-graph"),d("e"),d("tech-a"),True)
    with pytest.raises(GraphQuorumError):
        evaluate_graph_quorum_v0(graph=g,policy=p,attestations=(wrong_graph,))
    with pytest.raises(GraphQuorumError):
        evaluate_graph_quorum_v0(graph=g,policy=p,attestations=(att(g,"ka",d("wrong-tech")),))


def test_zero_edge_evidence_rejected_when_required():
    a=TrustGraphNodeV0("ka",1,d("ka-bind"),d("tech-a"))
    b=TrustGraphNodeV0("vor",1,d("vor-bind"),d("tech-b"))
    g=build_library_trust_graph_v0(nodes=(a,b),edges=(TrustGraphEdgeV0("ka","vor",d("r"),b"\x00"*32),))
    with pytest.raises(GraphQuorumError):
        evaluate_graph_quorum_v0(graph=g,policy=QuorumPolicyV0(1),attestations=(att(g,"ka",d("tech-a")),))
