"""Koschei Library trust graph v0.

A library activation may depend on several roots. This graph binds each root to
its concrete technology binding and binds root-to-root composition explicitly.
No edge is inferred. Missing roots, duplicate identities, generation drift,
technology drift and dangling composition edges fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .library_root_technology_binding_v0 import RootTechnologyBindingV0

_CTX=b"koschei.library-trust-graph/v0\x00"

class LibraryTrustGraphError(ValueError): pass

@dataclass(frozen=True,slots=True)
class TrustGraphNodeV0:
    root_id:str
    generation:int
    root_binding_digest:bytes
    technology_digest:bytes

@dataclass(frozen=True,slots=True)
class TrustGraphEdgeV0:
    source_root_id:str
    target_root_id:str
    relation_digest:bytes
    evidence_digest:bytes

@dataclass(frozen=True,slots=True)
class LibraryTrustGraphV0:
    nodes:tuple[TrustGraphNodeV0,...]
    edges:tuple[TrustGraphEdgeV0,...]
    graph_digest:bytes
    authority:bool=False


def _d32(v:bytes,name:str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32:
        raise LibraryTrustGraphError(f"{name} must be exactly 32 bytes")
    return v


def node_from_binding_v0(binding:RootTechnologyBindingV0)->TrustGraphNodeV0:
    if not isinstance(binding,RootTechnologyBindingV0) or binding.authority:
        raise LibraryTrustGraphError("authority-free root technology binding required")
    return TrustGraphNodeV0(
        binding.root_id,
        binding.generation,
        _d32(binding.root_binding_digest,"root_binding_digest"),
        _d32(binding.technology_digest,"technology_digest"),
    )


def build_library_trust_graph_v0(*,nodes:tuple[TrustGraphNodeV0,...],edges:tuple[TrustGraphEdgeV0,...]=())->LibraryTrustGraphV0:
    if not isinstance(nodes,tuple) or not nodes:
        raise LibraryTrustGraphError("non-empty immutable node tuple required")
    if not isinstance(edges,tuple):
        raise LibraryTrustGraphError("immutable edge tuple required")
    identities=[n.root_id for n in nodes]
    if any(not isinstance(i,str) or not i for i in identities):
        raise LibraryTrustGraphError("invalid root identity")
    if len(identities)!=len(set(identities)):
        raise LibraryTrustGraphError("duplicate root identity forbidden")
    known=set(identities)
    node_keys=set()
    for n in nodes:
        if not isinstance(n,TrustGraphNodeV0) or n.generation<1:
            raise LibraryTrustGraphError("invalid graph node")
        _d32(n.root_binding_digest,"root_binding_digest"); _d32(n.technology_digest,"technology_digest")
        key=(n.root_id,n.generation,n.root_binding_digest,n.technology_digest)
        if key in node_keys: raise LibraryTrustGraphError("duplicate graph node forbidden")
        node_keys.add(key)
    edge_keys=set()
    for e in edges:
        if not isinstance(e,TrustGraphEdgeV0): raise LibraryTrustGraphError("invalid graph edge")
        if e.source_root_id not in known or e.target_root_id not in known or e.source_root_id==e.target_root_id:
            raise LibraryTrustGraphError("composition edge must bind distinct known roots")
        _d32(e.relation_digest,"relation_digest"); _d32(e.evidence_digest,"evidence_digest")
        key=(e.source_root_id,e.target_root_id,e.relation_digest,e.evidence_digest)
        if key in edge_keys: raise LibraryTrustGraphError("duplicate composition edge forbidden")
        edge_keys.add(key)
    h=hashlib.sha3_256(_CTX)
    for n in sorted(nodes,key=lambda x:(x.root_id,x.generation,x.root_binding_digest,x.technology_digest)):
        h.update(b"N\x00"+n.root_id.encode()+b"\x00"+n.generation.to_bytes(8,"big")+n.root_binding_digest+n.technology_digest)
    for e in sorted(edges,key=lambda x:(x.source_root_id,x.target_root_id,x.relation_digest,x.evidence_digest)):
        h.update(b"E\x00"+e.source_root_id.encode()+b"\x00"+e.target_root_id.encode()+b"\x00"+e.relation_digest+e.evidence_digest)
    return LibraryTrustGraphV0(nodes,edges,h.digest(),False)


def verify_library_trust_graph_v0(graph:LibraryTrustGraphV0)->bool:
    if not isinstance(graph,LibraryTrustGraphV0) or graph.authority:
        return False
    try:
        rebuilt=build_library_trust_graph_v0(nodes=graph.nodes,edges=graph.edges)
    except LibraryTrustGraphError:
        return False
    return rebuilt.graph_digest==graph.graph_digest
