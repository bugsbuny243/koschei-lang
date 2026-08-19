"""Koschei Surface Graph v2.

A declarative, capability-free UI/runtime graph for Koschei applications.
This intentionally avoids Canvas/DOM/JavaScript-shaped draw commands. A surface
program declares entities, relationships, reactive signals, constraints and
visual intents. Native or browser hosts decide how to rasterize the graph.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib

_CTX=b"koschei.surface-graph/v2\x00"

class SurfaceGraphError(ValueError): pass

@dataclass(frozen=True, slots=True)
class SurfaceEntityV2:
    entity_id: str
    role: str
    parent_id: str|None
    traits: tuple[str,...]

@dataclass(frozen=True, slots=True)
class SurfaceSignalV2:
    signal_id: str
    source: str
    value_kind: str

@dataclass(frozen=True, slots=True)
class SurfaceBindingV2:
    entity_id: str
    property_name: str
    signal_id: str
    transform: str

@dataclass(frozen=True, slots=True)
class SurfaceRelationV2:
    source_id: str
    destination_id: str
    relation: str

@dataclass(frozen=True, slots=True)
class SurfaceConstraintV2:
    subject_id: str
    constraint: str
    object_id: str|None
    value_milli: int

@dataclass(frozen=True, slots=True)
class SurfaceGraphV2:
    entities: tuple[SurfaceEntityV2,...]
    signals: tuple[SurfaceSignalV2,...]
    bindings: tuple[SurfaceBindingV2,...]
    relations: tuple[SurfaceRelationV2,...]
    constraints: tuple[SurfaceConstraintV2,...]
    graph_digest: bytes
    authority: bool=False

_ALLOWED_ROLES=frozenset({"surface","world","node","portal","field","label","panel","input"})
_ALLOWED_RELATIONS=frozenset({"contains","links","guards","observes","persists","flows","isolates"})
_ALLOWED_SOURCES=frozenset({"observer","clock","input","constant"})
_ALLOWED_VALUE_KINDS=frozenset({"bool","i64","text","digest","ratio"})
_ALLOWED_TRANSFORMS=frozenset({"identity","pulse","normalize","status","phase","presence"})
_ALLOWED_CONSTRAINTS=frozenset({"anchor","orbit","separate","inside","outside","follow","bounded","visible-if"})

def _text(v:str,name:str,max_len:int=128)->str:
    if not isinstance(v,str) or not v or len(v)>max_len or "\x00" in v:
        raise SurfaceGraphError(f"invalid {name}")
    return v

def build_surface_graph_v2(*,entities:tuple[SurfaceEntityV2,...],signals:tuple[SurfaceSignalV2,...]=(),bindings:tuple[SurfaceBindingV2,...]=(),relations:tuple[SurfaceRelationV2,...]=(),constraints:tuple[SurfaceConstraintV2,...]=())->SurfaceGraphV2:
    if not all(isinstance(x,tuple) for x in (entities,signals,bindings,relations,constraints)):
        raise SurfaceGraphError("surface collections must be immutable tuples")
    if len(entities)>8192 or len(signals)>8192 or len(bindings)>32768 or len(relations)>32768 or len(constraints)>32768:
        raise SurfaceGraphError("surface graph budget exceeded")
    ids=set(); parent_refs=[]
    h=hashlib.sha3_256(_CTX)
    for e in sorted(entities,key=lambda x:x.entity_id):
        _text(e.entity_id,"entity id"); _text(e.role,"entity role")
        if e.role not in _ALLOWED_ROLES: raise SurfaceGraphError("unknown entity role")
        if e.entity_id in ids: raise SurfaceGraphError("duplicate entity id")
        ids.add(e.entity_id)
        if e.parent_id is not None: parent_refs.append(e.parent_id)
        for t in e.traits: _text(t,"trait",64)
        h.update(b"E\x00"+e.entity_id.encode()+b"\x00"+e.role.encode()+b"\x00"+(e.parent_id or "").encode()+b"\x00"+b"\x1f".join(t.encode() for t in e.traits))
    if any(p not in ids for p in parent_refs): raise SurfaceGraphError("unknown parent entity")
    signal_ids=set()
    for s in sorted(signals,key=lambda x:x.signal_id):
        _text(s.signal_id,"signal id");
        if s.source not in _ALLOWED_SOURCES or s.value_kind not in _ALLOWED_VALUE_KINDS: raise SurfaceGraphError("unsupported signal")
        if s.signal_id in signal_ids: raise SurfaceGraphError("duplicate signal id")
        signal_ids.add(s.signal_id); h.update(b"S\x00"+s.signal_id.encode()+b"\x00"+s.source.encode()+b"\x00"+s.value_kind.encode())
    for b in sorted(bindings,key=lambda x:(x.entity_id,x.property_name,x.signal_id,x.transform)):
        if b.entity_id not in ids or b.signal_id not in signal_ids: raise SurfaceGraphError("binding references unknown id")
        _text(b.property_name,"property",64)
        if b.transform not in _ALLOWED_TRANSFORMS: raise SurfaceGraphError("unsupported transform")
        h.update(b"B\x00"+b.entity_id.encode()+b"\x00"+b.property_name.encode()+b"\x00"+b.signal_id.encode()+b"\x00"+b.transform.encode())
    for r in sorted(relations,key=lambda x:(x.source_id,x.destination_id,x.relation)):
        if r.source_id not in ids or r.destination_id not in ids or r.relation not in _ALLOWED_RELATIONS: raise SurfaceGraphError("invalid surface relation")
        h.update(b"R\x00"+r.source_id.encode()+b"\x00"+r.destination_id.encode()+b"\x00"+r.relation.encode())
    for c in sorted(constraints,key=lambda x:(x.subject_id,x.constraint,x.object_id or "",x.value_milli)):
        if c.subject_id not in ids or (c.object_id is not None and c.object_id not in ids): raise SurfaceGraphError("constraint references unknown entity")
        if c.constraint not in _ALLOWED_CONSTRAINTS: raise SurfaceGraphError("unsupported constraint")
        if not isinstance(c.value_milli,int) or not(-(1<<31)<=c.value_milli<(1<<31)): raise SurfaceGraphError("constraint value out of range")
        h.update(b"C\x00"+c.subject_id.encode()+b"\x00"+c.constraint.encode()+b"\x00"+(c.object_id or "").encode()+b"\x00"+c.value_milli.to_bytes(4,"big",signed=True))
    return SurfaceGraphV2(tuple(sorted(entities,key=lambda x:x.entity_id)),tuple(sorted(signals,key=lambda x:x.signal_id)),tuple(sorted(bindings,key=lambda x:(x.entity_id,x.property_name,x.signal_id,x.transform))),tuple(sorted(relations,key=lambda x:(x.source_id,x.destination_id,x.relation))),tuple(sorted(constraints,key=lambda x:(x.subject_id,x.constraint,x.object_id or "",x.value_milli))),h.digest(),False)
