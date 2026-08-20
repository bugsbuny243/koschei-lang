import hashlib
import pytest

from koschei.library_trust_graph_v0 import (
    LibraryTrustGraphError,
    TrustGraphEdgeV0,
    TrustGraphNodeV0,
    build_library_trust_graph_v0,
    verify_library_trust_graph_v0,
)


def d(x:str)->bytes:
    return hashlib.sha3_256(x.encode()).digest()


def node(name:str,generation:int=1)->TrustGraphNodeV0:
    return TrustGraphNodeV0(name,generation,d(name+':root'),d(name+':tech'))


def test_graph_digest_is_order_independent():
    a,b=node('ka'),node('vor')
    e=TrustGraphEdgeV0('ka','vor',d('compose'),d('evidence'))
    g1=build_library_trust_graph_v0(nodes=(a,b),edges=(e,))
    g2=build_library_trust_graph_v0(nodes=(b,a),edges=(e,))
    assert g1.graph_digest==g2.graph_digest
    assert verify_library_trust_graph_v0(g1)


def test_technology_drift_changes_graph():
    a=node('ka')
    changed=TrustGraphNodeV0('ka',1,a.root_binding_digest,d('different-tech'))
    g1=build_library_trust_graph_v0(nodes=(a,))
    g2=build_library_trust_graph_v0(nodes=(changed,))
    assert g1.graph_digest!=g2.graph_digest


def test_generation_drift_changes_graph():
    assert build_library_trust_graph_v0(nodes=(node('ka',1),)).graph_digest != build_library_trust_graph_v0(nodes=(node('ka',2),)).graph_digest


def test_dangling_edge_fails_closed():
    with pytest.raises(LibraryTrustGraphError):
        build_library_trust_graph_v0(nodes=(node('ka'),),edges=(TrustGraphEdgeV0('ka','vor',d('r'),d('e')),))


def test_duplicate_root_id_fails_closed():
    with pytest.raises(LibraryTrustGraphError):
        build_library_trust_graph_v0(nodes=(node('ka',1),node('ka',2)))
