import pytest

from koschei.universe_projection_v1 import UniverseNodeV1, UniverseEdgeV1, project_universe_v1
from koschei.universe_live_state_v1 import UniverseEventV1, bind_live_state_v1
from koschei.universe_web_v1 import UniverseWebError, universe_payload_v1

P=b"p"*32; N1=b"1"*32; N2=b"2"*32; E=b"e"*32


def sample():
    projection=project_universe_v1(
        project_digest=P, epoch=4,
        nodes=(UniverseNodeV1("home","project",N1),UniverseNodeV1("db","storage",N2)),
        edges=(UniverseEdgeV1("home","db","persists",E),),
    )
    live=bind_live_state_v1(
        projection=projection,
        events=(UniverseEventV1("db","quarantine",b"q"*32,4),),
    )
    return projection,live


def test_payload_is_authority_free_and_binds_live_state():
    projection,live=sample(); payload=universe_payload_v1(projection=projection,live=live)
    assert payload["authority"] is False
    db=next(n for n in payload["nodes"] if n["id"]=="db")
    assert db["events"][0]["kind"]=="quarantine"
    assert payload["projection"]==projection.projection_digest.hex()
    assert payload["state"]==live.state_digest.hex()


def test_mismatched_projection_fails_closed():
    projection,live=sample()
    other=project_universe_v1(project_digest=b"x"*32,epoch=4,nodes=projection.nodes,edges=projection.edges)
    with pytest.raises(UniverseWebError):
        universe_payload_v1(projection=other,live=live)


def test_renderer_payload_contains_no_callable_or_secret_surface():
    projection,live=sample(); payload=universe_payload_v1(projection=projection,live=live)
    text=repr(payload).lower()
    assert "secret" not in text
    assert "private_key" not in text
    assert "grant" not in text
