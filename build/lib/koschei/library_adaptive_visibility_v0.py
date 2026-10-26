"""Koschei Library adaptive visibility envelope v0.

Derives an observer-scoped, epoch-bound visibility envelope from a verified
learning-resistance decision. The envelope never reveals private semantic corpus
or grants authority. As reconnaissance pressure rises, visible root/relation
budgets and diagnostic detail shrink. Compartment identifiers rotate by epoch and
session so accumulated maps cannot be treated as stable global topology.

This layer performs no counterattack and no external action.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib

from .library_adversary_learning_resistance_v0 import (
    LearningResistanceDecisionV0, VisibilityPosture,
)

_CTX=b"koschei.library-adaptive-visibility/v0\x00"

class AdaptiveVisibilityError(ValueError): pass

@dataclass(frozen=True,slots=True)
class VisibilityPolicyV0:
    normal_root_budget:int
    reduced_root_budget:int
    minimal_root_budget:int
    normal_relation_budget:int
    reduced_relation_budget:int
    minimal_relation_budget:int
    epoch_span_ticks:int
    rotate_compartments:bool=True
    authority:bool=False

@dataclass(frozen=True,slots=True)
class AdaptiveVisibilityEnvelopeV0:
    observer_id:str
    session_digest:bytes
    learning_decision_digest:bytes
    visibility_epoch:int
    root_budget:int
    relation_budget:int
    diagnostic_detail_ceiling:int
    stable_topology_labels:bool
    compartment_seed_digest:bytes
    envelope_digest:bytes
    allowed:bool
    authority:bool=False


def _d32(v:bytes,name:str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32:
        raise AdaptiveVisibilityError(f"{name} must be exactly 32 bytes")
    return v


def _validate_policy(p:VisibilityPolicyV0)->None:
    if not isinstance(p,VisibilityPolicyV0) or p.authority:
        raise AdaptiveVisibilityError("authority-free visibility policy required")
    vals=(p.normal_root_budget,p.reduced_root_budget,p.minimal_root_budget,
          p.normal_relation_budget,p.reduced_relation_budget,p.minimal_relation_budget,p.epoch_span_ticks)
    if any(not isinstance(v,int) or v<1 for v in vals):
        raise AdaptiveVisibilityError("visibility budgets and epoch span must be positive integers")
    if not (p.normal_root_budget>=p.reduced_root_budget>=p.minimal_root_budget):
        raise AdaptiveVisibilityError("root budgets must monotonically shrink")
    if not (p.normal_relation_budget>=p.reduced_relation_budget>=p.minimal_relation_budget):
        raise AdaptiveVisibilityError("relation budgets must monotonically shrink")


def derive_adaptive_visibility_v0(*,decision:LearningResistanceDecisionV0,policy:VisibilityPolicyV0,current_tick:int,rotation_secret_commitment:bytes)->AdaptiveVisibilityEnvelopeV0:
    _validate_policy(policy)
    if not isinstance(decision,LearningResistanceDecisionV0) or decision.authority:
        raise AdaptiveVisibilityError("authority-free learning-resistance decision required")
    if not isinstance(current_tick,int) or current_tick<decision.window_end_tick:
        raise AdaptiveVisibilityError("current_tick cannot precede learning decision")
    session=_d32(decision.session_digest,"session_digest")
    dd=_d32(decision.decision_digest,"decision_digest")
    secret=_d32(rotation_secret_commitment,"rotation_secret_commitment")
    if secret==b"\x00"*32:
        raise AdaptiveVisibilityError("rotation secret commitment cannot be empty")

    epoch=current_tick//policy.epoch_span_ticks
    if decision.posture is VisibilityPosture.CONTAINED or not decision.allowed:
        roots=0; relations=0; detail=0; allowed=False
    elif decision.posture is VisibilityPosture.MINIMAL:
        roots=policy.minimal_root_budget; relations=policy.minimal_relation_budget
        detail=min(1,decision.exposed_detail_ceiling); allowed=True
    elif decision.posture is VisibilityPosture.REDUCED:
        roots=policy.reduced_root_budget; relations=policy.reduced_relation_budget
        detail=min(2,decision.exposed_detail_ceiling); allowed=True
    else:
        roots=policy.normal_root_budget; relations=policy.normal_relation_budget
        detail=min(3,decision.exposed_detail_ceiling); allowed=True

    # Stable topology labels are intentionally disabled whenever compartment
    # rotation is enabled. This is observer-scoped presentation, not mutation of
    # the canonical trust graph or execution authority.
    stable_labels=not policy.rotate_compartments
    seed=hashlib.sha3_256(
        _CTX+b"compartment\x00"+decision.observer_id.encode()+b"\x00"+session
        +epoch.to_bytes(8,"big")+dd+secret
    ).digest()
    h=hashlib.sha3_256(
        _CTX+b"envelope\x00"+decision.observer_id.encode()+b"\x00"+session+dd
        +epoch.to_bytes(8,"big")+roots.to_bytes(8,"big")+relations.to_bytes(8,"big")
        +detail.to_bytes(2,"big")+(b"\x01" if stable_labels else b"\x00")+seed
        +(b"OK" if allowed else b"DENY")
    ).digest()
    return AdaptiveVisibilityEnvelopeV0(
        decision.observer_id,session,dd,epoch,roots,relations,detail,stable_labels,seed,h,allowed,False
    )


def derive_compartment_alias_v0(*,envelope:AdaptiveVisibilityEnvelopeV0,canonical_subject_digest:bytes,ordinal:int)->bytes:
    if not isinstance(envelope,AdaptiveVisibilityEnvelopeV0) or envelope.authority or not envelope.allowed:
        raise AdaptiveVisibilityError("allowed authority-free visibility envelope required")
    subject=_d32(canonical_subject_digest,"canonical_subject_digest")
    if subject==b"\x00"*32:
        raise AdaptiveVisibilityError("canonical subject digest cannot be empty")
    if not isinstance(ordinal,int) or ordinal<0:
        raise AdaptiveVisibilityError("ordinal must be non-negative")
    return hashlib.sha3_256(
        _CTX+b"alias\x00"+envelope.compartment_seed_digest+subject+ordinal.to_bytes(8,"big")
    ).digest()
