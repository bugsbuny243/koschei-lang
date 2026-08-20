"""Koschei Library containment optimizer v0.

Given a verified trust graph and a derived blast radius, choose a deterministic
containment cut that maximizes protected safe-service value while respecting an
explicit disruption budget. The optimizer is authority-free and performs no
external action; it only derives a canonical containment recommendation.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib

from .library_trust_graph_v0 import LibraryTrustGraphV0, verify_library_trust_graph_v0
from .library_blast_radius_v0 import BlastRadiusV0

_CTX=b"koschei.library-containment-optimizer/v0\x00"

class ContainmentOptimizerError(ValueError): pass

@dataclass(frozen=True,slots=True)
class RootServiceWeightV0:
    root_id:str
    service_value:int
    disruption_cost:int

@dataclass(frozen=True,slots=True)
class ContainmentPolicyV0:
    max_disruption_cost:int
    require_full_boundary_cut:bool=True
    authority:bool=False

@dataclass(frozen=True,slots=True)
class ContainmentRecommendationV0:
    graph_digest:bytes
    radius_digest:bytes
    cut_edges:tuple[tuple[str,str],...]
    preserved_roots:tuple[str,...]
    isolated_roots:tuple[str,...]
    preserved_service_value:int
    disruption_cost:int
    recommendation_digest:bytes
    feasible:bool
    authority:bool=False


def _d32(v:bytes,name:str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32:
        raise ContainmentOptimizerError(f"{name} must be exactly 32 bytes")
    return v


def optimize_containment_v0(*,graph:LibraryTrustGraphV0,radius:BlastRadiusV0,weights:tuple[RootServiceWeightV0,...],policy:ContainmentPolicyV0)->ContainmentRecommendationV0:
    if not verify_library_trust_graph_v0(graph):
        raise ContainmentOptimizerError("verified canonical trust graph required")
    if not isinstance(radius,BlastRadiusV0) or radius.authority:
        raise ContainmentOptimizerError("authority-free blast radius required")
    if radius.graph_digest!=graph.graph_digest:
        raise ContainmentOptimizerError("blast-radius/graph mismatch")
    if not isinstance(weights,tuple) or not isinstance(policy,ContainmentPolicyV0) or policy.authority:
        raise ContainmentOptimizerError("immutable weights and authority-free policy required")
    if not isinstance(policy.max_disruption_cost,int) or policy.max_disruption_cost<0:
        raise ContainmentOptimizerError("invalid disruption budget")

    known={n.root_id for n in graph.nodes}
    seen=set(); by_root={}
    for w in weights:
        if not isinstance(w,RootServiceWeightV0) or w.root_id not in known or w.root_id in seen:
            raise ContainmentOptimizerError("weights must name distinct known roots")
        if not isinstance(w.service_value,int) or not isinstance(w.disruption_cost,int) or w.service_value<0 or w.disruption_cost<0:
            raise ContainmentOptimizerError("service/disruption weights must be non-negative integers")
        seen.add(w.root_id); by_root[w.root_id]=w
    if seen!=known:
        raise ContainmentOptimizerError("weights required for every graph root")

    affected=set(radius.affected_roots)
    safe=set(radius.safe_roots)
    if affected & safe or affected | safe != known:
        raise ContainmentOptimizerError("blast radius root partition invalid")

    # Fail-closed default: every affected root is isolated. Service loss is the
    # explicit cost attached to isolated roots; safe roots remain preserved.
    isolated=set(affected)
    preserved=set(safe)
    disruption=sum(by_root[r].disruption_cost for r in isolated)
    service_value=sum(by_root[r].service_value for r in preserved)
    cut=set(radius.boundary_cut_edges)

    # If policy does not require the complete boundary cut, we still never allow
    # a path from affected to safe roots. Therefore v0 keeps the same minimal
    # graph-theoretic boundary and only relaxes policy metadata for future modes.
    feasible=disruption<=policy.max_disruption_cost
    if not feasible:
        # Never silently weaken containment to satisfy availability budget.
        preserved= set()
        service_value=0

    h=hashlib.sha3_256(_CTX+graph.graph_digest+_d32(radius.radius_digest,"radius_digest"))
    h.update(policy.max_disruption_cost.to_bytes(8,"big"))
    h.update(b"\x01" if policy.require_full_boundary_cut else b"\x00")
    for r in sorted(known):
        w=by_root[r]
        h.update(b"W\x00"+r.encode()+b"\x00"+w.service_value.to_bytes(8,"big")+w.disruption_cost.to_bytes(8,"big"))
    for src,dst in sorted(cut): h.update(b"C\x00"+src.encode()+b"\x00"+dst.encode()+b"\x00")
    for r in sorted(preserved): h.update(b"P\x00"+r.encode()+b"\x00")
    for r in sorted(isolated): h.update(b"I\x00"+r.encode()+b"\x00")
    h.update(service_value.to_bytes(8,"big")+disruption.to_bytes(8,"big")+(b"OK" if feasible else b"DENY"))
    return ContainmentRecommendationV0(
        graph.graph_digest,radius.radius_digest,tuple(sorted(cut)),tuple(sorted(preserved)),
        tuple(sorted(isolated)),service_value,disruption,h.digest(),feasible,False
    )
