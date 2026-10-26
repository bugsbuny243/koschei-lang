"""Koschei Library multi-scenario containment planner v0.

Merges several independently derived containment scenarios that belong to the
same canonical trust graph. The result is conservative: isolated roots and cut
edges are unioned, preserved roots are the remaining safe roots, and any
infeasible scenario makes the combined recommendation infeasible. This module
is authority-free and performs no external action.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib

from .library_trust_graph_v0 import LibraryTrustGraphV0, verify_library_trust_graph_v0
from .library_containment_optimizer_v0 import ContainmentRecommendationV0

_CTX=b"koschei.library-multi-scenario-containment/v0\x00"

class MultiScenarioContainmentError(ValueError): pass

@dataclass(frozen=True,slots=True)
class MultiScenarioContainmentV0:
    graph_digest:bytes
    scenario_digests:tuple[bytes,...]
    isolated_roots:tuple[str,...]
    preserved_roots:tuple[str,...]
    cut_edges:tuple[tuple[str,str],...]
    combined_digest:bytes
    feasible:bool
    authority:bool=False


def _d32(v:bytes,name:str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32:
        raise MultiScenarioContainmentError(f"{name} must be exactly 32 bytes")
    return v


def combine_containment_scenarios_v0(*,graph:LibraryTrustGraphV0,scenarios:tuple[ContainmentRecommendationV0,...])->MultiScenarioContainmentV0:
    if not verify_library_trust_graph_v0(graph):
        raise MultiScenarioContainmentError("verified canonical trust graph required")
    if not isinstance(scenarios,tuple) or not scenarios:
        raise MultiScenarioContainmentError("non-empty immutable scenario tuple required")

    known={n.root_id for n in graph.nodes}
    isolated=set(); cuts=set(); digests=[]; seen=set(); feasible=True
    for s in sorted(scenarios,key=lambda x:x.recommendation_digest if isinstance(x,ContainmentRecommendationV0) else b""):
        if not isinstance(s,ContainmentRecommendationV0) or s.authority:
            raise MultiScenarioContainmentError("authority-free containment recommendation required")
        if s.graph_digest!=graph.graph_digest:
            raise MultiScenarioContainmentError("scenario/graph mismatch")
        sd=_d32(s.recommendation_digest,"recommendation_digest")
        if sd in seen:
            raise MultiScenarioContainmentError("duplicate containment scenario forbidden")
        seen.add(sd); digests.append(sd)
        roots=set(s.isolated_roots)
        if not roots.issubset(known):
            raise MultiScenarioContainmentError("scenario isolates unknown root")
        isolated.update(roots)
        for src,dst in s.cut_edges:
            if src not in known or dst not in known or src==dst:
                raise MultiScenarioContainmentError("invalid scenario cut edge")
            cuts.add((src,dst))
        feasible=feasible and s.feasible

    # Conservative combined containment: anything isolated in any valid scenario
    # remains isolated. A preserved root must therefore survive every scenario.
    preserved=known-isolated if feasible else set()

    h=hashlib.sha3_256(_CTX+graph.graph_digest)
    for d in sorted(digests): h.update(b"S\x00"+d)
    for rid in sorted(isolated): h.update(b"I\x00"+rid.encode()+b"\x00")
    for rid in sorted(preserved): h.update(b"P\x00"+rid.encode()+b"\x00")
    for src,dst in sorted(cuts): h.update(b"C\x00"+src.encode()+b"\x00"+dst.encode()+b"\x00")
    h.update(b"OK" if feasible else b"DENY")
    return MultiScenarioContainmentV0(
        graph.graph_digest,tuple(sorted(digests)),tuple(sorted(isolated)),
        tuple(sorted(preserved)),tuple(sorted(cuts)),h.digest(),feasible,False
    )
