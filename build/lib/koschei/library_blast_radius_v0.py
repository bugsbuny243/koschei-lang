"""Koschei Library blast-radius and dependency-cut analysis v0.

Given a verified trust graph and a compromise recovery plan, derive the smallest
conservative root set reachable from quarantined roots and the boundary edges
that must be cut to isolate that set. This layer is authority-free and never
performs external actions; it only derives deterministic containment evidence.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib

from .library_trust_graph_v0 import LibraryTrustGraphV0, verify_library_trust_graph_v0
from .library_compromise_recovery_v0 import RecoveryPlanV0

_CTX=b"koschei.library-blast-radius/v0\x00"

class BlastRadiusError(ValueError): pass

@dataclass(frozen=True,slots=True)
class BlastRadiusV0:
    graph_digest:bytes
    recovery_plan_digest:bytes
    compromised_roots:tuple[str,...]
    affected_roots:tuple[str,...]
    internal_edges:tuple[tuple[str,str],...]
    boundary_cut_edges:tuple[tuple[str,str],...]
    safe_roots:tuple[str,...]
    radius_digest:bytes
    authority:bool=False


def _d32(v:bytes,name:str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32:
        raise BlastRadiusError(f"{name} must be exactly 32 bytes")
    return v


def derive_blast_radius_v0(*,graph:LibraryTrustGraphV0,plan:RecoveryPlanV0,max_hops:int|None=None)->BlastRadiusV0:
    if not verify_library_trust_graph_v0(graph):
        raise BlastRadiusError("verified canonical trust graph required")
    if not isinstance(plan,RecoveryPlanV0) or plan.authority:
        raise BlastRadiusError("authority-free recovery plan required")
    if _d32(plan.graph_digest,"plan.graph_digest")!=graph.graph_digest:
        raise BlastRadiusError("recovery plan/graph mismatch")
    if max_hops is not None and (not isinstance(max_hops,int) or max_hops<0):
        raise BlastRadiusError("max_hops must be non-negative or None")
    known={n.root_id for n in graph.nodes}
    compromised=set(plan.quarantined_roots)
    if not compromised or not compromised.issubset(known):
        raise BlastRadiusError("recovery plan contains invalid quarantined roots")

    # Treat composition as bidirectional for containment analysis. A relation in
    # either direction means the two roots share a trust/composition boundary.
    adjacency={rid:set() for rid in known}
    edges=[]
    for e in graph.edges:
        adjacency[e.source_root_id].add(e.target_root_id)
        adjacency[e.target_root_id].add(e.source_root_id)
        edges.append((e.source_root_id,e.target_root_id))

    affected=set(compromised)
    frontier=set(compromised)
    hops=0
    while frontier and (max_hops is None or hops<max_hops):
        nxt=set()
        for rid in sorted(frontier):
            for nb in adjacency[rid]:
                if nb not in affected:
                    affected.add(nb); nxt.add(nb)
        frontier=nxt; hops+=1

    internal=set(); boundary=set()
    for src,dst in edges:
        s=src in affected; d=dst in affected
        if s and d:
            internal.add((src,dst))
        elif s != d:
            boundary.add((src,dst))
    safe=known-affected

    h=hashlib.sha3_256(_CTX+graph.graph_digest+plan.plan_digest)
    h.update((0xffffffffffffffff if max_hops is None else max_hops).to_bytes(8,"big"))
    for rid in sorted(compromised): h.update(b"C\x00"+rid.encode()+b"\x00")
    for rid in sorted(affected): h.update(b"A\x00"+rid.encode()+b"\x00")
    for src,dst in sorted(internal): h.update(b"I\x00"+src.encode()+b"\x00"+dst.encode()+b"\x00")
    for src,dst in sorted(boundary): h.update(b"B\x00"+src.encode()+b"\x00"+dst.encode()+b"\x00")
    for rid in sorted(safe): h.update(b"S\x00"+rid.encode()+b"\x00")
    return BlastRadiusV0(graph.graph_digest,plan.plan_digest,tuple(sorted(compromised)),tuple(sorted(affected)),tuple(sorted(internal)),tuple(sorted(boundary)),tuple(sorted(safe)),h.digest(),False)
