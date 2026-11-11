"""Native Koschei Surface source grammar v1.

This is a small declarative Koschei subgrammar for authority-free presentation
state. It is intentionally not HTML, DOM, CSS, Canvas, or JavaScript syntax.

Grammar:

    surface <name> {
      entity <id> <anchor|body|field|trace|region|intent>
      relation <source> <orbits|binds|guards|flows|contains|witnesses> <target>
      signal <id> <observation|intent|clock|state> <signed-int>
      constraint <subject> <distance|phase|visibility|capacity|isolation> <signed-int>
    }

Statements are topology facts, not imperative draw commands. The compiler emits
SurfaceTopologyV1 and cannot mint runtime authority.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import re

from .surface_topology_v1 import (
    ConstraintNature,
    EntityNature,
    RelationNature,
    SignalNature,
    SurfaceConstraintV1,
    SurfaceEntityV1,
    SurfaceRelationV1,
    SurfaceSignalV1,
    SurfaceTopologyV1,
    build_surface_topology_v1,
)

_CTX=b"koschei.surface-source/v1\x00"
_ID=re.compile(r"^[a-z][a-z0-9_]{0,63}$")

class SurfaceSourceError(SyntaxError): pass

@dataclass(frozen=True,slots=True)
class SurfaceSourceV1:
    name:str
    topology:SurfaceTopologyV1
    source_digest:bytes
    authority:bool=False

def _evidence(kind:str,parts:tuple[str,...])->bytes:
    h=hashlib.sha3_256(_CTX+kind.encode()+b"\x00")
    for p in parts:
        b=p.encode("utf-8");h.update(len(b).to_bytes(2,"big"));h.update(b)
    return h.digest()

def _identifier(value:str,line:int)->str:
    if not _ID.fullmatch(value):
        raise SurfaceSourceError(f"line {line}: invalid Koschei Surface identifier {value!r}")
    return value

def _signed_int(value:str,line:int)->int:
    if not re.fullmatch(r"-?(0|[1-9][0-9]{0,17})",value):
        raise SurfaceSourceError(f"line {line}: expected bounded signed integer")
    n=int(value)
    if not (-(1<<63)<=n<(1<<63)):
        raise SurfaceSourceError(f"line {line}: value outside signed i64")
    return n

def compile_surface_source_v1(source:str)->SurfaceSourceV1:
    if not isinstance(source,str): raise SurfaceSourceError("surface source must be text")
    raw=[]
    for lineno,line in enumerate(source.splitlines(),1):
        body=line.split("//",1)[0].strip()
        if body: raw.append((lineno,body))
    if len(raw)<2: raise SurfaceSourceError("surface block required")
    first_line,first=raw[0]
    m=re.fullmatch(r"surface\s+([a-z][a-z0-9_]{0,63})\s*\{",first)
    if not m: raise SurfaceSourceError(f"line {first_line}: expected 'surface <name> {{'")
    name=m.group(1)
    if raw[-1][1]!="}": raise SurfaceSourceError(f"line {raw[-1][0]}: surface block must end with '}}'")
    entities=[];relations=[];signals=[];constraints=[]
    seen_entity=set();seen_signal=set()
    for lineno,text in raw[1:-1]:
        if "{" in text or "}" in text or ";" in text:
            raise SurfaceSourceError(f"line {lineno}: nested blocks and statement separators are not Surface syntax")
        parts=tuple(text.split())
        if not parts: continue
        head=parts[0]
        try:
            if head=="entity" and len(parts)==3:
                ident=_identifier(parts[1],lineno);nature=EntityNature(parts[2])
                if ident in seen_entity: raise SurfaceSourceError(f"line {lineno}: duplicate entity {ident}")
                seen_entity.add(ident)
                entities.append(SurfaceEntityV1(ident,nature,_evidence("entity",parts[1:])))
            elif head=="relation" and len(parts)==4:
                src=_identifier(parts[1],lineno);nature=RelationNature(parts[2]);dst=_identifier(parts[3],lineno)
                relations.append(SurfaceRelationV1(src,dst,nature,_evidence("relation",parts[1:])))
            elif head=="signal" and len(parts)==4:
                ident=_identifier(parts[1],lineno);nature=SignalNature(parts[2]);value=_signed_int(parts[3],lineno)
                if ident in seen_signal: raise SurfaceSourceError(f"line {lineno}: duplicate signal {ident}")
                seen_signal.add(ident)
                signals.append(SurfaceSignalV1(ident,nature,value,_evidence("signal",parts[1:])))
            elif head=="constraint" and len(parts)==4:
                subject=_identifier(parts[1],lineno);nature=ConstraintNature(parts[2]);value=_signed_int(parts[3],lineno)
                constraints.append(SurfaceConstraintV1(subject,nature,value,_evidence("constraint",parts[1:])))
            else:
                raise SurfaceSourceError(f"line {lineno}: unknown Surface topology statement")
        except ValueError as exc:
            raise SurfaceSourceError(f"line {lineno}: invalid Surface nature") from exc
    topology=build_surface_topology_v1(entities=tuple(entities),relations=tuple(relations),signals=tuple(signals),constraints=tuple(constraints))
    normalized=[f"surface {name} {{"]
    normalized += ["entity "+e.identity+" "+e.nature.value for e in sorted(entities,key=lambda x:x.identity)]
    normalized += ["relation "+r.source+" "+r.nature.value+" "+r.target for r in sorted(relations,key=lambda x:(x.source,x.nature.value,x.target))]
    normalized += ["signal "+s.identity+" "+s.nature.value+" "+str(s.value_milli) for s in sorted(signals,key=lambda x:x.identity)]
    normalized += ["constraint "+c.subject+" "+c.nature.value+" "+str(c.value_milli) for c in sorted(constraints,key=lambda x:(x.subject,x.nature.value,x.value_milli))]
    normalized.append("}")
    digest=hashlib.sha3_256(_CTX+"\n".join(normalized).encode("utf-8")).digest()
    return SurfaceSourceV1(name,topology,digest,False)
