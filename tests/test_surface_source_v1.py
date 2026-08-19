import pytest

from koschei.surface_source_v1 import SurfaceSourceError, compile_surface_source_v1


def test_surface_source_compiles_native_topology():
    src='''
surface universe {
  entity core anchor
  entity shield field
  entity lane trace
  relation core guards shield
  relation core flows lane
  signal activity state 1000
  constraint shield isolation 1000
}
'''
    out=compile_surface_source_v1(src)
    assert out.name=='universe'
    assert out.authority is False
    assert out.topology.authority is False
    assert {e.identity for e in out.topology.entities}=={'core','shield','lane'}
    assert len(out.topology.relations)==2
    assert len(out.source_digest)==32
    assert len(out.topology.topology_digest)==32


def test_surface_source_is_order_canonical():
    a='''surface u {
entity a anchor
entity b field
relation a guards b
signal pulse state 5
constraint b isolation 1
}'''
    b='''surface u {
signal pulse state 5
entity b field
constraint b isolation 1
entity a anchor
relation a guards b
}'''
    assert compile_surface_source_v1(a).source_digest==compile_surface_source_v1(b).source_digest
    assert compile_surface_source_v1(a).topology.topology_digest==compile_surface_source_v1(b).topology.topology_digest


def test_surface_source_rejects_unknown_html_js_canvas_shapes():
    bad=(
        'surface u {\ndiv root\n}',
        'surface u {\ncanvas world\n}',
        'surface u {\nscript eval\n}',
        'surface u {\nentity root anchor;\n}',
    )
    for src in bad:
        with pytest.raises(SurfaceSourceError):
            compile_surface_source_v1(src)


def test_surface_source_rejects_relation_to_unknown_entity_fail_closed():
    with pytest.raises(ValueError):
        compile_surface_source_v1('''surface u {
entity core anchor
relation core guards ghost
}''')
