"""Koschei Library graph activation quorum v0.

A graph cannot become active because one root is locally valid. Activation is
bound to the canonical graph digest and to explicit, authority-free attestations
for distinct graph roots. Threshold policy is explicit; missing, duplicate,
unknown, stale or graph-mismatched attestations fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .library_trust_graph_v0 import LibraryTrustGraphV0, verify_library_trust_graph_v0

_CTX=b"koschei.library-graph-quorum/v0\x00"

class GraphQuorumError(ValueError): pass

@dataclass(frozen=True,slots=True)
class RootAttestationV0:
    root_id:str
    generation:int
    graph_digest:bytes
    evidence_digest:bytes
    technology_digest:bytes
    accepted:bool
    authority:bool=False

@dataclass(frozen=True,slots=True)
class QuorumPolicyV0:
    threshold:int
    require_all_edges_evidenced:bool=True
    authority:bool=False

@dataclass(frozen=True,slots=True)
class GraphActivationDecisionV0:
    graph_digest:bytes
    threshold:int
    accepted_roots:tuple[str,...]
    decision_digest:bytes
    active:bool
    authority:bool=False


def _d32(v:bytes,name:str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32:
        raise GraphQuorumError(f"{name} must be exactly 32 bytes")
    return v


def evaluate_graph_quorum_v0(*,graph:LibraryTrustGraphV0,policy:QuorumPolicyV0,attestations:tuple[RootAttestationV0,...])->GraphActivationDecisionV0:
    if not verify_library_trust_graph_v0(graph):
        raise GraphQuorumError("verified canonical trust graph required")
    if not isinstance(policy,QuorumPolicyV0) or policy.authority:
        raise GraphQuorumError("authority-free quorum policy required")
    if not isinstance(attestations,tuple):
        raise GraphQuorumError("immutable attestation tuple required")
    if policy.threshold<1 or policy.threshold>len(graph.nodes):
        raise GraphQuorumError("quorum threshold outside graph bounds")
    by_root={n.root_id:n for n in graph.nodes}
    seen=set(); accepted=[]; parts=[]
    for a in sorted(attestations,key=lambda x:(x.root_id,x.generation,x.evidence_digest)):
        if not isinstance(a,RootAttestationV0) or a.authority:
            raise GraphQuorumError("invalid root attestation")
        if a.root_id in seen:
            raise GraphQuorumError("duplicate root attestation forbidden")
        seen.add(a.root_id)
        n=by_root.get(a.root_id)
        if n is None:
            raise GraphQuorumError("attestation for unknown root")
        if a.generation!=n.generation:
            raise GraphQuorumError("root generation mismatch")
        if _d32(a.graph_digest,"graph_digest")!=graph.graph_digest:
            raise GraphQuorumError("attestation bound to different graph")
        if _d32(a.technology_digest,"technology_digest")!=n.technology_digest:
            raise GraphQuorumError("technology attestation mismatch")
        ev=_d32(a.evidence_digest,"evidence_digest")
        parts.append(a.root_id.encode()+b"\x00"+a.generation.to_bytes(8,"big")+ev+a.technology_digest+(b"\x01" if a.accepted else b"\x00"))
        if a.accepted: accepted.append(a.root_id)
    if policy.require_all_edges_evidenced and graph.edges:
        # Edge evidence already belongs to the canonical graph; reject empty/zero evidence
        # so a composition relation cannot participate without an explicit evidence root.
        for e in graph.edges:
            if e.evidence_digest==b"\x00"*32:
                raise GraphQuorumError("composition edge missing evidence")
    active=len(accepted)>=policy.threshold
    h=hashlib.sha3_256(_CTX+graph.graph_digest+policy.threshold.to_bytes(4,"big")+(b"\x01" if policy.require_all_edges_evidenced else b"\x00"))
    for p in parts:
        h.update(len(p).to_bytes(4,"big")); h.update(p)
    h.update(b"ACTIVE" if active else b"DENIED")
    return GraphActivationDecisionV0(graph.graph_digest,policy.threshold,tuple(sorted(accepted)),h.digest(),active,False)
