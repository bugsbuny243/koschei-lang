"""Koschei Surface topology kernel v1.

Not a DOM, HTML tree, CSS box model, canvas command list, or JavaScript object
model. A Surface is an immutable authority-free topology whose observable
presentation is derived from entities, relations, signals and constraints.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib

_CTX=b"koschei.surface-topology/v1\x00"

class SurfaceTopologyError(ValueError): pass

class EntityNature(str,Enum):
    ANCHOR="anchor"
    BODY="body"
    FIELD="field"
    TRACE="trace"
    REGION="region"
    INTENT="intent"

class RelationNature(str,Enum):
    ORBITS="orbits"
    BINDS="binds"
    GUARDS="guards"
    FLOWS="flows"
    CONTAINS="contains"
    WITNESSES="witnesses"

class SignalNature(str,Enum):
    OBSERVATION="observation"
    INTENT="intent"
    CLOCK="clock"
    STATE="state"

class ConstraintNature(str,Enum):
    DISTANCE="distance"
    PHASE="phase"
    VISIBILITY="visibility"
    CAPACITY="capacity"
    ISOLATION="isolation"

@dataclass(frozen=True,slots=True)
class SurfaceEntityV1:
    identity:str
    nature:EntityNature
    evidence_digest:bytes

@dataclass(frozen=True,slots=True)
class SurfaceRelationV1:
    source:str
    target:str
    nature:RelationNature
    evidence_digest:bytes

@dataclass(frozen=True,slots=True)
class SurfaceSignalV1:
    identity:str
    nature:SignalNature
    value_milli:int
    evidence_digest:bytes

@dataclass(frozen=True,slots=True)
class SurfaceConstraintV1:
    subject:str
    nature:ConstraintNature
    value_milli:int
    evidence_digest:bytes

@dataclass(frozen=True,slots=True)
class SurfaceTopologyV1:
    entities:tuple[SurfaceEntityV1,...]
    relations:tuple[SurfaceRelationV1,...]
    signals:tuple[SurfaceSignalV1,...]
    constraints:tuple[SurfaceConstraintV1,...]
    topology_digest:bytes
    authority:bool=False

def _digest_parts(parts:list[bytes])->bytes:
    h=hashlib.sha3_256(_CTX)
    for p in parts:
        h.update(len(p).to_bytes(4,"big"));h.update(p)
    return h.digest()

def build_surface_topology_v1(*,entities:tuple[SurfaceEntityV1,...],relations:tuple[SurfaceRelationV1,...]=(),signals:tuple[SurfaceSignalV1,...]=(),constraints:tuple[SurfaceConstraintV1,...]=())->SurfaceTopologyV1:
    if not all(isinstance(v,tuple) for v in (entities,relations,signals,constraints)): raise SurfaceTopologyError("surface collections must be immutable tuples")
    ids=[e.identity for e in entities]
    if not ids or len(ids)!=len(set(ids)) or any(not i for i in ids): raise SurfaceTopologyError("surface entity identities must be non-empty and unique")
    known=set(ids)
    for r in relations:
        if r.source not in known or r.target not in known or r.source==r.target: raise SurfaceTopologyError("relation must bind distinct known entities")
    for c in constraints:
        if c.subject not in known: raise SurfaceTopologyError("constraint subject must be a known entity")
    signal_ids=[s.identity for s in signals]
    if len(signal_ids)!=len(set(signal_ids)): raise SurfaceTopologyError("signal identities must be unique")
    parts=[]
    for e in sorted(entities,key=lambda x:x.identity): parts += [b"E",e.identity.encode(),e.nature.value.encode(),e.evidence_digest]
    for r in sorted(relations,key=lambda x:(x.source,x.target,x.nature.value)): parts += [b"R",r.source.encode(),r.target.encode(),r.nature.value.encode(),r.evidence_digest]
    for s in sorted(signals,key=lambda x:x.identity): parts += [b"S",s.identity.encode(),s.nature.value.encode(),str(s.value_milli).encode(),s.evidence_digest]
    for c in sorted(constraints,key=lambda x:(x.subject,x.nature.value)): parts += [b"C",c.subject.encode(),c.nature.value.encode(),str(c.value_milli).encode(),c.evidence_digest]
    return SurfaceTopologyV1(entities,relations,signals,constraints,_digest_parts(parts),False)
