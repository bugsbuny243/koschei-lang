import pytest
from koschei.loki_adaptive_topology_v1 import (
    AdaptiveTopologyError, derive_decoy_route_v1,
    route_is_non_authoritative_v1, topology_rotates_v1,
)

O=b"o"*32; E=b"e"*32; N=b"n"*32

def test_same_evidence_replays_same_auditable_route():
    a=derive_decoy_route_v1(observer_digest=O,evidence_digest=E,generation=3,surface="cache")
    b=derive_decoy_route_v1(observer_digest=O,evidence_digest=E,generation=3,surface="cache")
    assert a == b
    assert route_is_non_authoritative_v1(a)

def test_new_evidence_requires_topology_rotation():
    a=derive_decoy_route_v1(observer_digest=O,evidence_digest=E,generation=3,surface="cache")
    assert topology_rotates_v1(a,new_evidence_digest=N)
    assert not topology_rotates_v1(a,new_evidence_digest=E)

def test_decoy_cannot_impersonate_privileged_surfaces():
    for surface in ("root", "vormir", "signing-secret", "execute-gateway"):
        with pytest.raises(AdaptiveTopologyError):
            derive_decoy_route_v1(observer_digest=O,evidence_digest=E,generation=0,surface=surface)

def test_observer_changes_route_without_granting_power():
    a=derive_decoy_route_v1(observer_digest=O,evidence_digest=E,generation=1,surface="registry")
    b=derive_decoy_route_v1(observer_digest=b"x"*32,evidence_digest=E,generation=1,surface="registry")
    assert a.route_digest != b.route_digest
    assert not a.authority and not b.authority
