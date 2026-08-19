"""Koschei Library technology core v0.

The hidden library is not a story corpus. This module defines the technical
substrate that every future Koschei root must bind to: canonical commitments,
capability denial by default, provenance, quantum-safe algorithm agility,
information-flow labels, deterministic budgets, isolation and fail-closed
admission. It is intentionally independent of React/npm/DOM/HTML/CSS/JS models.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib

_CTX=b"koschei.library-technology-core/v0\x00"

class TechnologyCoreError(ValueError): pass

class TrustClass(str,Enum):
    UNTRUSTED="untrusted"
    VERIFIED="verified"
    ATTESTED="attested"

class FlowClass(str,Enum):
    PUBLIC="public"
    SENSITIVE="sensitive"
    SECRET="secret"
    ROOT="root"

class IsolationClass(str,Enum):
    NONE="none"
    PROCESS="process"
    SANDBOX="sandbox"
    HARDWARE="hardware"

@dataclass(frozen=True,slots=True)
class AlgorithmSuiteV0:
    classical_kem:str
    pq_kem:str
    classical_signature:str
    pq_signature:str
    digest:str="sha3-256"

@dataclass(frozen=True,slots=True)
class ProvenanceV0:
    source_digest:bytes
    build_digest:bytes
    toolchain_digest:bytes
    policy_digest:bytes

@dataclass(frozen=True,slots=True)
class CapabilityEnvelopeV0:
    subject_digest:bytes
    scope_digest:bytes
    expires_epoch:int
    delegable:bool=False
    ambient:bool=False

@dataclass(frozen=True,slots=True)
class FlowLabelV0:
    data_digest:bytes
    classification:FlowClass
    origin_digest:bytes

@dataclass(frozen=True,slots=True)
class ExecutionBudgetV0:
    instruction_limit:int
    memory_limit_bytes:int
    io_limit_bytes:int
    deadline_millis:int

@dataclass(frozen=True,slots=True)
class TechnologyBindingV0:
    algorithms:AlgorithmSuiteV0
    provenance:ProvenanceV0
    trust:TrustClass
    isolation:IsolationClass
    budget:ExecutionBudgetV0
    binding_digest:bytes
    authority:bool=False


def _d32(v:bytes,name:str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32: raise TechnologyCoreError(f"{name} must be exactly 32 bytes")
    return v

def _text(v:str,name:str)->bytes:
    if not isinstance(v,str) or not v or len(v)>96: raise TechnologyCoreError(f"invalid {name}")
    return v.encode("utf-8")

def bind_technology_core_v0(*,algorithms:AlgorithmSuiteV0,provenance:ProvenanceV0,trust:TrustClass,isolation:IsolationClass,budget:ExecutionBudgetV0)->TechnologyBindingV0:
    if not isinstance(algorithms,AlgorithmSuiteV0): raise TechnologyCoreError("algorithm suite required")
    if not isinstance(provenance,ProvenanceV0): raise TechnologyCoreError("provenance required")
    if not isinstance(trust,TrustClass) or not isinstance(isolation,IsolationClass): raise TechnologyCoreError("canonical trust and isolation required")
    if not isinstance(budget,ExecutionBudgetV0): raise TechnologyCoreError("execution budget required")
    if trust is TrustClass.UNTRUSTED and isolation is IsolationClass.NONE: raise TechnologyCoreError("untrusted execution must be isolated")
    if min(budget.instruction_limit,budget.memory_limit_bytes,budget.io_limit_bytes,budget.deadline_millis)<=0: raise TechnologyCoreError("all execution budgets must be positive")
    if budget.memory_limit_bytes>1<<40 or budget.io_limit_bytes>1<<40: raise TechnologyCoreError("execution budget exceeds hard safety ceiling")
    parts=[_CTX,_text(algorithms.classical_kem,"classical_kem"),_text(algorithms.pq_kem,"pq_kem"),_text(algorithms.classical_signature,"classical_signature"),_text(algorithms.pq_signature,"pq_signature"),_text(algorithms.digest,"digest"),_d32(provenance.source_digest,"source_digest"),_d32(provenance.build_digest,"build_digest"),_d32(provenance.toolchain_digest,"toolchain_digest"),_d32(provenance.policy_digest,"policy_digest"),trust.value.encode(),isolation.value.encode(),budget.instruction_limit.to_bytes(8,"big"),budget.memory_limit_bytes.to_bytes(8,"big"),budget.io_limit_bytes.to_bytes(8,"big"),budget.deadline_millis.to_bytes(8,"big")]
    h=hashlib.sha3_256()
    for p in parts: h.update(len(p).to_bytes(4,"big"));h.update(p)
    return TechnologyBindingV0(algorithms,provenance,trust,isolation,budget,h.digest(),False)

def validate_capability_v0(cap:CapabilityEnvelopeV0,*,current_epoch:int)->bool:
    if not isinstance(cap,CapabilityEnvelopeV0) or current_epoch<0: return False
    if cap.ambient or cap.delegable: return False
    if cap.expires_epoch<current_epoch: return False
    return len(cap.subject_digest)==32 and len(cap.scope_digest)==32

def permits_flow_v0(label:FlowLabelV0,*,sink_max:FlowClass)->bool:
    if not isinstance(label,FlowLabelV0) or not isinstance(sink_max,FlowClass): return False
    if len(label.data_digest)!=32 or len(label.origin_digest)!=32: return False
    rank={FlowClass.PUBLIC:0,FlowClass.SENSITIVE:1,FlowClass.SECRET:2,FlowClass.ROOT:3}
    return rank[label.classification] <= rank[sink_max]
