"""Koschei Library compromise recovery v0.

Canonical, fail-closed recovery planning for suspected key/root compromise.
This layer never attacks external systems and never grants authority. It derives
which graph roots and relations must be quarantined, which generations must be
revoked, and what evidence is required before recovery can close.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib

from .library_trust_graph_v0 import LibraryTrustGraphV0, verify_library_trust_graph_v0

_CTX=b"koschei.library-compromise-recovery/v0\x00"

class CompromiseRecoveryError(ValueError): pass

class CompromiseClass(str,Enum):
    KEY="key"
    ROOT="root"
    TECHNOLOGY="technology"
    EVIDENCE="evidence"

@dataclass(frozen=True,slots=True)
class CompromiseSignalV0:
    subject_id:str
    generation:int
    compromise_class:CompromiseClass
    evidence_digest:bytes
    detected_epoch:int

@dataclass(frozen=True,slots=True)
class RecoveryPlanV0:
    graph_digest:bytes
    detected_epoch:int
    quarantined_roots:tuple[str,...]
    revoked_generations:tuple[tuple[str,int],...]
    disabled_edges:tuple[tuple[str,str],...]
    required_evidence:tuple[bytes,...]
    plan_digest:bytes
    authority:bool=False

@dataclass(frozen=True,slots=True)
class RecoveryClosureV0:
    plan_digest:bytes
    replacement_graph_digest:bytes
    closure_epoch:int
    evidence_digest:bytes
    closure_digest:bytes
    closed:bool
    authority:bool=False


def _d32(v:bytes,name:str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32:
        raise CompromiseRecoveryError(f"{name} must be exactly 32 bytes")
    return v


def derive_recovery_plan_v0(*,graph:LibraryTrustGraphV0,signals:tuple[CompromiseSignalV0,...],detected_epoch:int)->RecoveryPlanV0:
    if not verify_library_trust_graph_v0(graph):
        raise CompromiseRecoveryError("verified canonical trust graph required")
    if not isinstance(signals,tuple) or not signals:
        raise CompromiseRecoveryError("non-empty immutable compromise signals required")
    if not isinstance(detected_epoch,int) or detected_epoch<1:
        raise CompromiseRecoveryError("detected_epoch must be positive")
    by_root={n.root_id:n for n in graph.nodes}
    seen=set(); quarantine=set(); revoked=set(); evidence=[]
    for s in sorted(signals,key=lambda x:(x.subject_id,x.generation,x.compromise_class.value,x.evidence_digest)):
        if not isinstance(s,CompromiseSignalV0) or not isinstance(s.compromise_class,CompromiseClass):
            raise CompromiseRecoveryError("invalid compromise signal")
        n=by_root.get(s.subject_id)
        if n is None:
            raise CompromiseRecoveryError("compromise signal references unknown root")
        if s.generation!=n.generation:
            raise CompromiseRecoveryError("compromise signal generation mismatch")
        if s.detected_epoch<1 or s.detected_epoch>detected_epoch:
            raise CompromiseRecoveryError("compromise signal epoch invalid")
        ev=_d32(s.evidence_digest,"evidence_digest")
        if ev==b"\x00"*32:
            raise CompromiseRecoveryError("compromise evidence cannot be empty")
        key=(s.subject_id,s.generation,s.compromise_class.value,ev)
        if key in seen:
            raise CompromiseRecoveryError("duplicate compromise signal forbidden")
        seen.add(key); quarantine.add(s.subject_id); revoked.add((s.subject_id,s.generation)); evidence.append(ev)
    # Disable every relation touching a quarantined root. This avoids assuming
    # that a compromised root remains safe merely because its neighbor is valid.
    disabled=set()
    for e in graph.edges:
        if e.source_root_id in quarantine or e.target_root_id in quarantine:
            disabled.add((e.source_root_id,e.target_root_id))
            evidence.append(_d32(e.evidence_digest,"edge.evidence_digest"))
    h=hashlib.sha3_256(_CTX+b"plan\x00"+graph.graph_digest+detected_epoch.to_bytes(8,"big"))
    for rid in sorted(quarantine): h.update(b"Q\x00"+rid.encode()+b"\x00")
    for rid,gen in sorted(revoked): h.update(b"R\x00"+rid.encode()+b"\x00"+gen.to_bytes(8,"big"))
    for src,dst in sorted(disabled): h.update(b"E\x00"+src.encode()+b"\x00"+dst.encode()+b"\x00")
    for ev in sorted(set(evidence)): h.update(b"V\x00"+ev)
    return RecoveryPlanV0(graph.graph_digest,detected_epoch,tuple(sorted(quarantine)),tuple(sorted(revoked)),tuple(sorted(disabled)),tuple(sorted(set(evidence))),h.digest(),False)


def close_recovery_v0(*,plan:RecoveryPlanV0,replacement_graph:LibraryTrustGraphV0,closure_epoch:int,evidence_digest:bytes)->RecoveryClosureV0:
    if not isinstance(plan,RecoveryPlanV0) or plan.authority:
        raise CompromiseRecoveryError("authority-free recovery plan required")
    if not verify_library_trust_graph_v0(replacement_graph):
        raise CompromiseRecoveryError("verified replacement graph required")
    if not isinstance(closure_epoch,int) or closure_epoch<plan.detected_epoch:
        raise CompromiseRecoveryError("closure epoch precedes compromise detection")
    ev=_d32(evidence_digest,"evidence_digest")
    if ev==b"\x00"*32:
        raise CompromiseRecoveryError("recovery closure requires non-empty evidence")
    # A recovery cannot close by replaying the compromised graph unchanged.
    if replacement_graph.graph_digest==plan.graph_digest:
        raise CompromiseRecoveryError("replacement graph must differ from compromised graph")
    old_revoked=set(plan.revoked_generations)
    new_nodes={n.root_id:n for n in replacement_graph.nodes}
    for rid,gen in old_revoked:
        n=new_nodes.get(rid)
        if n is not None and n.generation<=gen:
            raise CompromiseRecoveryError("revoked root must be removed or advance generation")
    material=(_CTX+b"close\x00"+plan.plan_digest+replacement_graph.graph_digest+closure_epoch.to_bytes(8,"big")+ev)
    digest=hashlib.sha3_256(material).digest()
    return RecoveryClosureV0(plan.plan_digest,replacement_graph.graph_digest,closure_epoch,ev,digest,True,False)
