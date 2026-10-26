"""Koschei Library policy-conflict resolution and recovery-priority graph v0.

When several recovery/containment policies coexist, this layer derives a
canonical execution order without weakening safety. Hard safety dependencies
must be acyclic, explicit, graph-bound and evidence-bound. Conflicting recovery
steps are resolved by deterministic precedence; impossible or cyclic plans fail
closed. This module grants no runtime authority and performs no external action.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib

from .library_trust_graph_v0 import LibraryTrustGraphV0, verify_library_trust_graph_v0
from .library_multi_scenario_containment_v0 import MultiScenarioContainmentV0

_CTX=b"koschei.library-policy-conflict-resolution/v0\x00"

class PolicyConflictResolutionError(ValueError): pass

class RecoveryPriority(str,Enum):
    CRITICAL="critical"
    HIGH="high"
    NORMAL="normal"
    LOW="low"

@dataclass(frozen=True,slots=True)
class RecoveryStepV0:
    step_id:str
    root_id:str
    action_digest:bytes
    evidence_digest:bytes
    priority:RecoveryPriority
    destructive:bool=False

@dataclass(frozen=True,slots=True)
class RecoveryDependencyV0:
    before_step_id:str
    after_step_id:str
    evidence_digest:bytes

@dataclass(frozen=True,slots=True)
class RecoveryPriorityPlanV0:
    graph_digest:bytes
    containment_digest:bytes
    ordered_step_ids:tuple[str,...]
    dependency_edges:tuple[tuple[str,str],...]
    deferred_step_ids:tuple[str,...]
    plan_digest:bytes
    executable:bool
    authority:bool=False


def _d32(v:bytes,name:str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32:
        raise PolicyConflictResolutionError(f"{name} must be exactly 32 bytes")
    return v


def _priority_rank(p:RecoveryPriority)->int:
    return {
        RecoveryPriority.CRITICAL:0,
        RecoveryPriority.HIGH:1,
        RecoveryPriority.NORMAL:2,
        RecoveryPriority.LOW:3,
    }[p]


def resolve_recovery_priorities_v0(*,graph:LibraryTrustGraphV0,containment:MultiScenarioContainmentV0,steps:tuple[RecoveryStepV0,...],dependencies:tuple[RecoveryDependencyV0,...]=())->RecoveryPriorityPlanV0:
    if not verify_library_trust_graph_v0(graph):
        raise PolicyConflictResolutionError("verified canonical trust graph required")
    if not isinstance(containment,MultiScenarioContainmentV0) or containment.authority:
        raise PolicyConflictResolutionError("authority-free multi-scenario containment required")
    if containment.graph_digest!=graph.graph_digest:
        raise PolicyConflictResolutionError("containment/graph mismatch")
    if not containment.feasible:
        raise PolicyConflictResolutionError("infeasible containment cannot produce executable recovery")
    if not isinstance(steps,tuple) or not steps:
        raise PolicyConflictResolutionError("non-empty immutable recovery steps required")
    if not isinstance(dependencies,tuple):
        raise PolicyConflictResolutionError("immutable dependency tuple required")

    known_roots={n.root_id for n in graph.nodes}
    by_id={}; action_keys=set()
    for s in steps:
        if not isinstance(s,RecoveryStepV0) or not s.step_id or len(s.step_id)>96:
            raise PolicyConflictResolutionError("invalid recovery step")
        if s.step_id in by_id:
            raise PolicyConflictResolutionError("duplicate recovery step id forbidden")
        if s.root_id not in known_roots:
            raise PolicyConflictResolutionError("recovery step references unknown root")
        if not isinstance(s.priority,RecoveryPriority):
            raise PolicyConflictResolutionError("canonical recovery priority required")
        ad=_d32(s.action_digest,"action_digest"); ev=_d32(s.evidence_digest,"evidence_digest")
        if ev==b"\x00"*32:
            raise PolicyConflictResolutionError("recovery step evidence cannot be empty")
        # Same root + same action digest must not appear twice under different ids.
        ak=(s.root_id,ad)
        if ak in action_keys:
            raise PolicyConflictResolutionError("duplicate recovery action forbidden")
        action_keys.add(ak); by_id[s.step_id]=s

    edges=set(); indegree={sid:0 for sid in by_id}; outgoing={sid:set() for sid in by_id}
    for d in dependencies:
        if not isinstance(d,RecoveryDependencyV0):
            raise PolicyConflictResolutionError("invalid recovery dependency")
        if d.before_step_id not in by_id or d.after_step_id not in by_id or d.before_step_id==d.after_step_id:
            raise PolicyConflictResolutionError("dependency must bind distinct known steps")
        ev=_d32(d.evidence_digest,"dependency.evidence_digest")
        if ev==b"\x00"*32:
            raise PolicyConflictResolutionError("dependency evidence cannot be empty")
        edge=(d.before_step_id,d.after_step_id)
        if edge in edges:
            raise PolicyConflictResolutionError("duplicate recovery dependency forbidden")
        edges.add(edge); outgoing[edge[0]].add(edge[1]); indegree[edge[1]]+=1

    # Kahn topological ordering with deterministic safety-first tie breaking.
    # Destructive operations are delayed behind non-destructive operations of the
    # same priority unless an explicit dependency says otherwise.
    ready=[sid for sid,v in indegree.items() if v==0]
    ordered=[]
    while ready:
        ready.sort(key=lambda sid:(_priority_rank(by_id[sid].priority), by_id[sid].destructive, sid))
        sid=ready.pop(0); ordered.append(sid)
        for dst in sorted(outgoing[sid]):
            indegree[dst]-=1
            if indegree[dst]==0: ready.append(dst)
    if len(ordered)!=len(by_id):
        raise PolicyConflictResolutionError("cyclic recovery dependency graph forbidden")

    isolated=set(containment.isolated_roots)
    deferred=tuple(sorted(
        s.step_id for s in steps
        if s.root_id not in isolated and s.priority is RecoveryPriority.LOW
    ))
    final_order=tuple(sid for sid in ordered if sid not in set(deferred)) + deferred

    h=hashlib.sha3_256(_CTX+graph.graph_digest+_d32(containment.combined_digest,"containment.combined_digest"))
    for s in sorted(steps,key=lambda x:x.step_id):
        h.update(b"S\x00"+s.step_id.encode()+b"\x00"+s.root_id.encode()+b"\x00"+s.action_digest+s.evidence_digest+s.priority.value.encode()+ (b"\x01" if s.destructive else b"\x00"))
    for a,b in sorted(edges): h.update(b"D\x00"+a.encode()+b"\x00"+b.encode()+b"\x00")
    for sid in final_order: h.update(b"O\x00"+sid.encode()+b"\x00")
    for sid in deferred: h.update(b"F\x00"+sid.encode()+b"\x00")
    return RecoveryPriorityPlanV0(
        graph.graph_digest,containment.combined_digest,final_order,tuple(sorted(edges)),deferred,h.digest(),True,False
    )
