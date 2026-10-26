"""Koschei Library adversary-learning resistance v0.

Defensive, behavior-based control for high-speed reconnaissance and systematic
knowledge acquisition. It does not attempt to identify whether an actor is AI or
human. Instead it measures observable discovery behavior against explicit
knowledge-acquisition budgets and derives a fail-closed visibility posture.

This layer performs no counterattack, no external action and grants no authority.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib

_CTX=b"koschei.library-adversary-learning-resistance/v0\x00"

class AdversaryLearningResistanceError(ValueError): pass

class DiscoveryClass(str,Enum):
    ROOT_ENUMERATION="root_enumeration"
    RELATION_MAPPING="relation_mapping"
    AUTHORITY_PROBING="authority_probing"
    POLICY_PROBING="policy_probing"
    STATE_DIFFERENTIAL="state_differential"
    ERROR_ORACLE="error_oracle"
    TIMING_ORACLE="timing_oracle"

class VisibilityPosture(str,Enum):
    NORMAL="normal"
    REDUCED="reduced"
    MINIMAL="minimal"
    CONTAINED="contained"

@dataclass(frozen=True,slots=True)
class DiscoveryObservationV0:
    observer_id:str
    session_digest:bytes
    tick:int
    discovery_class:DiscoveryClass
    target_digest:bytes
    novelty_units:int
    boundary_attempt:bool=False
    evidence_digest:bytes=b""
    authority:bool=False

@dataclass(frozen=True,slots=True)
class KnowledgeBudgetV0:
    max_total_units:int
    max_distinct_targets:int
    max_boundary_attempts:int
    max_classes:int
    window_ticks:int
    reduced_ratio_per_mille:int=600
    minimal_ratio_per_mille:int=850
    authority:bool=False

@dataclass(frozen=True,slots=True)
class LearningResistanceDecisionV0:
    observer_id:str
    session_digest:bytes
    window_start_tick:int
    window_end_tick:int
    total_units:int
    distinct_targets:int
    boundary_attempts:int
    distinct_classes:int
    utilization_per_mille:int
    posture:VisibilityPosture
    exposed_detail_ceiling:int
    decision_digest:bytes
    allowed:bool
    authority:bool=False


def _d32(v:bytes,name:str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32:
        raise AdversaryLearningResistanceError(f"{name} must be exactly 32 bytes")
    return v


def _validate_budget(b:KnowledgeBudgetV0)->None:
    if not isinstance(b,KnowledgeBudgetV0) or b.authority:
        raise AdversaryLearningResistanceError("authority-free knowledge budget required")
    vals=(b.max_total_units,b.max_distinct_targets,b.max_boundary_attempts,b.max_classes,b.window_ticks)
    if any(not isinstance(v,int) or v<1 for v in vals):
        raise AdversaryLearningResistanceError("knowledge-budget limits must be positive integers")
    if not (1<=b.reduced_ratio_per_mille<b.minimal_ratio_per_mille<=1000):
        raise AdversaryLearningResistanceError("invalid posture thresholds")


def evaluate_learning_resistance_v0(*,observations:tuple[DiscoveryObservationV0,...],budget:KnowledgeBudgetV0,current_tick:int)->LearningResistanceDecisionV0:
    _validate_budget(budget)
    if not isinstance(observations,tuple) or not observations:
        raise AdversaryLearningResistanceError("non-empty immutable discovery observations required")
    if not isinstance(current_tick,int) or current_tick<0:
        raise AdversaryLearningResistanceError("current_tick must be non-negative")

    first=observations[0]
    if not isinstance(first,DiscoveryObservationV0) or first.authority:
        raise AdversaryLearningResistanceError("authority-free discovery observations required")
    observer_id=first.observer_id
    session=_d32(first.session_digest,"session_digest")
    if not observer_id or len(observer_id)>96:
        raise AdversaryLearningResistanceError("invalid observer identity")

    window_start=max(0,current_tick-budget.window_ticks+1)
    selected=[]; seen_event_keys=set()
    for o in observations:
        if not isinstance(o,DiscoveryObservationV0) or o.authority:
            raise AdversaryLearningResistanceError("authority-free discovery observations required")
        if o.observer_id!=observer_id or _d32(o.session_digest,"session_digest")!=session:
            raise AdversaryLearningResistanceError("mixed observer/session observations forbidden")
        if not isinstance(o.discovery_class,DiscoveryClass):
            raise AdversaryLearningResistanceError("canonical discovery class required")
        if not isinstance(o.tick,int) or o.tick<0 or o.tick>current_tick:
            raise AdversaryLearningResistanceError("invalid discovery observation tick")
        target=_d32(o.target_digest,"target_digest")
        evidence=_d32(o.evidence_digest,"evidence_digest")
        if target==b"\x00"*32 or evidence==b"\x00"*32:
            raise AdversaryLearningResistanceError("target/evidence digest cannot be empty")
        if not isinstance(o.novelty_units,int) or o.novelty_units<0 or o.novelty_units>1_000_000:
            raise AdversaryLearningResistanceError("invalid novelty units")
        key=(o.tick,o.discovery_class.value,target,evidence)
        if key in seen_event_keys:
            raise AdversaryLearningResistanceError("duplicate discovery observation forbidden")
        seen_event_keys.add(key)
        if o.tick>=window_start:
            selected.append(o)
    if not selected:
        raise AdversaryLearningResistanceError("no observations inside active knowledge window")

    total_units=sum(o.novelty_units for o in selected)
    targets={o.target_digest for o in selected}
    boundaries=sum(1 for o in selected if o.boundary_attempt)
    classes={o.discovery_class for o in selected}

    ratios=(
        (total_units*1000+budget.max_total_units-1)//budget.max_total_units,
        (len(targets)*1000+budget.max_distinct_targets-1)//budget.max_distinct_targets,
        (boundaries*1000+budget.max_boundary_attempts-1)//budget.max_boundary_attempts,
        (len(classes)*1000+budget.max_classes-1)//budget.max_classes,
    )
    utilization=max(ratios)
    exceeded=(
        total_units>budget.max_total_units or
        len(targets)>budget.max_distinct_targets or
        boundaries>budget.max_boundary_attempts or
        len(classes)>budget.max_classes
    )

    if exceeded:
        posture=VisibilityPosture.CONTAINED; detail=0; allowed=False
    elif utilization>=budget.minimal_ratio_per_mille:
        posture=VisibilityPosture.MINIMAL; detail=1; allowed=True
    elif utilization>=budget.reduced_ratio_per_mille:
        posture=VisibilityPosture.REDUCED; detail=2; allowed=True
    else:
        posture=VisibilityPosture.NORMAL; detail=3; allowed=True

    h=hashlib.sha3_256(
        _CTX+b"decision\x00"+observer_id.encode()+b"\x00"+session
        +window_start.to_bytes(8,"big")+current_tick.to_bytes(8,"big")
        +total_units.to_bytes(8,"big")+len(targets).to_bytes(8,"big")
        +boundaries.to_bytes(8,"big")+len(classes).to_bytes(8,"big")
        +utilization.to_bytes(8,"big")+posture.value.encode()+b"\x00"+detail.to_bytes(2,"big")
    )
    for o in sorted(selected,key=lambda x:(x.tick,x.discovery_class.value,x.target_digest,x.evidence_digest)):
        h.update(
            b"O\x00"+o.tick.to_bytes(8,"big")+o.discovery_class.value.encode()+b"\x00"
            +o.target_digest+o.novelty_units.to_bytes(8,"big")
            +(b"\x01" if o.boundary_attempt else b"\x00")+o.evidence_digest
        )
    return LearningResistanceDecisionV0(
        observer_id,session,window_start,current_tick,total_units,len(targets),boundaries,
        len(classes),utilization,posture,detail,h.digest(),allowed,False
    )
