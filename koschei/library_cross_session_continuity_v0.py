"""Koschei Library cross-session continuity resistance v0.

Prevents reconnaissance budgets from being trivially reset by opening fresh
sessions while avoiding publication of a stable raw user identity. A caller is
represented by a privacy-preserving continuity token derived from a rotating
secret commitment plus a bounded continuity anchor. Several session decisions
can then be aggregated into one conservative knowledge posture.

This module performs no counterattack, no external I/O, and grants no authority.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib

from .library_adversary_learning_resistance_v0 import (
    LearningResistanceDecisionV0, VisibilityPosture,
)

_CTX=b"koschei.library-cross-session-continuity/v0\x00"

class CrossSessionContinuityError(ValueError): pass

@dataclass(frozen=True,slots=True)
class ContinuityPolicyV0:
    epoch_span_ticks:int
    max_sessions_per_epoch:int
    max_combined_units:int
    max_combined_targets:int
    max_combined_boundary_attempts:int
    authority:bool=False

@dataclass(frozen=True,slots=True)
class ContinuityTokenV0:
    continuity_epoch:int
    token_digest:bytes
    anchor_commitment:bytes
    authority:bool=False

@dataclass(frozen=True,slots=True)
class CrossSessionDecisionV0:
    continuity_epoch:int
    token_digest:bytes
    session_digests:tuple[bytes,...]
    combined_units:int
    combined_targets_upper_bound:int
    combined_boundary_attempts:int
    session_count:int
    posture:VisibilityPosture
    allowed:bool
    decision_digest:bytes
    authority:bool=False


def _d32(v:bytes,name:str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32:
        raise CrossSessionContinuityError(f"{name} must be exactly 32 bytes")
    return v


def _validate_policy(p:ContinuityPolicyV0)->None:
    if not isinstance(p,ContinuityPolicyV0) or p.authority:
        raise CrossSessionContinuityError("authority-free continuity policy required")
    vals=(p.epoch_span_ticks,p.max_sessions_per_epoch,p.max_combined_units,
          p.max_combined_targets,p.max_combined_boundary_attempts)
    if any(not isinstance(v,int) or v<1 for v in vals):
        raise CrossSessionContinuityError("continuity limits must be positive integers")


def derive_continuity_token_v0(*,anchor_commitment:bytes,current_tick:int,policy:ContinuityPolicyV0,rotation_secret_commitment:bytes)->ContinuityTokenV0:
    _validate_policy(policy)
    if not isinstance(current_tick,int) or current_tick<0:
        raise CrossSessionContinuityError("current_tick must be non-negative")
    anchor=_d32(anchor_commitment,"anchor_commitment")
    secret=_d32(rotation_secret_commitment,"rotation_secret_commitment")
    if anchor==b"\x00"*32 or secret==b"\x00"*32:
        raise CrossSessionContinuityError("anchor/rotation commitments cannot be empty")
    epoch=current_tick//policy.epoch_span_ticks
    token=hashlib.sha3_256(
        _CTX+b"token\x00"+epoch.to_bytes(8,"big")+anchor+secret
    ).digest()
    return ContinuityTokenV0(epoch,token,anchor,False)


def aggregate_cross_session_learning_v0(*,token:ContinuityTokenV0,decisions:tuple[LearningResistanceDecisionV0,...],policy:ContinuityPolicyV0)->CrossSessionDecisionV0:
    _validate_policy(policy)
    if not isinstance(token,ContinuityTokenV0) or token.authority:
        raise CrossSessionContinuityError("authority-free continuity token required")
    td=_d32(token.token_digest,"token_digest")
    if not isinstance(decisions,tuple) or not decisions:
        raise CrossSessionContinuityError("non-empty immutable decision tuple required")

    sessions=set(); units=0; targets_ub=0; boundaries=0; worst=VisibilityPosture.NORMAL
    rank={VisibilityPosture.NORMAL:0,VisibilityPosture.REDUCED:1,VisibilityPosture.MINIMAL:2,VisibilityPosture.CONTAINED:3}
    for d in decisions:
        if not isinstance(d,LearningResistanceDecisionV0) or d.authority:
            raise CrossSessionContinuityError("authority-free learning decision required")
        sd=_d32(d.session_digest,"session_digest")
        if sd in sessions:
            raise CrossSessionContinuityError("duplicate session decision forbidden")
        sessions.add(sd)
        units+=d.total_units
        # Without exposing canonical target identities across sessions, use the
        # conservative sum as an upper bound instead of trying to correlate them.
        targets_ub+=d.distinct_targets
        boundaries+=d.boundary_attempts
        if rank[d.posture]>rank[worst]: worst=d.posture

    exceeded=(
        len(sessions)>policy.max_sessions_per_epoch or
        units>policy.max_combined_units or
        targets_ub>policy.max_combined_targets or
        boundaries>policy.max_combined_boundary_attempts
    )
    if exceeded:
        posture=VisibilityPosture.CONTAINED; allowed=False
    else:
        # Cross-session aggregation may only preserve or tighten the worst
        # individual session posture; it can never relax it.
        posture=worst; allowed=posture is not VisibilityPosture.CONTAINED

    ordered=tuple(sorted(sessions))
    h=hashlib.sha3_256(
        _CTX+b"decision\x00"+token.continuity_epoch.to_bytes(8,"big")+td
        +units.to_bytes(8,"big")+targets_ub.to_bytes(8,"big")
        +boundaries.to_bytes(8,"big")+len(ordered).to_bytes(8,"big")
        +posture.value.encode()+b"\x00"+(b"OK" if allowed else b"DENY")
    )
    for sd in ordered: h.update(b"S\x00"+sd)
    return CrossSessionDecisionV0(
        token.continuity_epoch,td,ordered,units,targets_ub,boundaries,len(ordered),
        posture,allowed,h.digest(),False
    )
