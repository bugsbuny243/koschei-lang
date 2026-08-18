import pytest

from koschei.universe_projection_v1 import UniverseEdgeV1, UniverseNodeV1, project_universe_v1
from koschei.universe_live_state_v1 import UniverseEventV1, UniverseLiveStateError, bind_live_state_v1

P=b"p"*32; N=b"n"*32; E=b"e"*32

def projection():
    return project_universe_v1(
        project_digest=P, epoch=4,
        nodes=(UniverseNodeV1("home","project",N), UniverseNodeV1("pkg","package",b"q"*32)),
        edges=(UniverseEdgeV1("home","pkg","depends",E),),
    )

def test_live_state_is_authority_free_and_bound_to_projection():
    p=projection()
    s=bind_live_state_v1(projection=p, events=(UniverseEventV1("pkg","portal-activity",b"a"*32,4),))
    assert s.projection_digest == p.projection_digest
    assert s.authority is False
    assert len(s.state_digest)==32

def test_unknown_node_or_event_kind_fails_closed():
    p=projection()
    with pytest.raises(UniverseLiveStateError):
        bind_live_state_v1(projection=p,events=(UniverseEventV1("ghost","quarantine",b"a"*32,4),))
    with pytest.raises(UniverseLiveStateError):
        bind_live_state_v1(projection=p,events=(UniverseEventV1("pkg","pretty-animation",b"a"*32,4),))

def test_stale_event_cannot_rewrite_current_view():
    with pytest.raises(UniverseLiveStateError):
        bind_live_state_v1(projection=projection(),events=(UniverseEventV1("pkg","fork",b"a"*32,3),))

def test_same_facts_are_deterministic_regardless_of_order():
    p=projection()
    rows=(UniverseEventV1("pkg","quarantine",b"a"*32,4),UniverseEventV1("home","admission-denied",b"b"*32,5))
    a=bind_live_state_v1(projection=p,events=rows)
    b=bind_live_state_v1(projection=p,events=tuple(reversed(rows)))
    assert a.state_digest == b.state_digest
