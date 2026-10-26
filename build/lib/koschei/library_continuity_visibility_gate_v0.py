"""Koschei Library continuity-aware visibility gate v0.

Binds an adaptive per-session visibility envelope to a conservative cross-session
continuity decision so opening fresh sessions cannot relax a stricter aggregate
posture. The gate only tightens visibility; it never expands authority or reveals
private continuity anchors.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib

from .library_adaptive_visibility_v0 import AdaptiveVisibilityEnvelopeV0
from .library_cross_session_continuity_v0 import CrossSessionDecisionV0
from .library_adversary_learning_resistance_v0 import VisibilityPosture

_CTX=b"koschei.library-continuity-visibility-gate/v0\x00"

class ContinuityVisibilityGateError(ValueError): pass

@dataclass(frozen=True,slots=True)
class ContinuityVisibilityGateV0:
    continuity_epoch:int
    continuity_decision_digest:bytes
    session_digest:bytes
    envelope_digest:bytes
    effective_posture:VisibilityPosture
    root_budget:int
    relation_budget:int
    diagnostic_detail_ceiling:int
    allowed:bool
    gate_digest:bytes
    authority:bool=False


def _d32(v:bytes,name:str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32:
        raise ContinuityVisibilityGateError(f"{name} must be exactly 32 bytes")
    return v


def _rank(p:VisibilityPosture)->int:
    return {
        VisibilityPosture.NORMAL:0,
        VisibilityPosture.REDUCED:1,
        VisibilityPosture.MINIMAL:2,
        VisibilityPosture.CONTAINED:3,
    }[p]


def bind_visibility_to_cross_session_v0(*,continuity:CrossSessionDecisionV0,envelope:AdaptiveVisibilityEnvelopeV0)->ContinuityVisibilityGateV0:
    if not isinstance(continuity,CrossSessionDecisionV0) or continuity.authority:
        raise ContinuityVisibilityGateError("authority-free cross-session decision required")
    if not isinstance(envelope,AdaptiveVisibilityEnvelopeV0) or envelope.authority:
        raise ContinuityVisibilityGateError("authority-free adaptive visibility envelope required")
    session=_d32(envelope.session_digest,"envelope.session_digest")
    if session not in continuity.session_digests:
        raise ContinuityVisibilityGateError("envelope session is not covered by continuity decision")
    cd=_d32(continuity.decision_digest,"continuity.decision_digest")
    ed=_d32(envelope.envelope_digest,"envelope.envelope_digest")

    # The aggregate cross-session decision may only tighten the per-session view.
    # We do not reconstruct hidden topology or mint a replacement authority.
    if not continuity.allowed or continuity.posture is VisibilityPosture.CONTAINED:
        posture=VisibilityPosture.CONTAINED
        roots=relations=detail=0
        allowed=False
    else:
        # Adaptive envelope already encoded the session posture into concrete
        # budgets. Cross-session REDUCED/MINIMAL cannot safely infer a larger
        # budget, so conservatively cap by ratios rather than expand it.
        posture=continuity.posture
        if posture is VisibilityPosture.MINIMAL:
            roots=0 if envelope.root_budget==0 else min(envelope.root_budget,1)
            relations=0 if envelope.relation_budget==0 else min(envelope.relation_budget,1)
            detail=min(envelope.diagnostic_detail_ceiling,1)
        elif posture is VisibilityPosture.REDUCED:
            roots=envelope.root_budget
            relations=envelope.relation_budget
            detail=min(envelope.diagnostic_detail_ceiling,2)
        else:
            roots=envelope.root_budget
            relations=envelope.relation_budget
            detail=envelope.diagnostic_detail_ceiling
        allowed=envelope.allowed and roots>=0 and relations>=0
        if not envelope.allowed:
            posture=VisibilityPosture.CONTAINED
            roots=relations=detail=0
            allowed=False

    h=hashlib.sha3_256(
        _CTX+b"gate\x00"+continuity.continuity_epoch.to_bytes(8,"big")+cd+session+ed
        +posture.value.encode()+b"\x00"+roots.to_bytes(8,"big")+relations.to_bytes(8,"big")
        +detail.to_bytes(2,"big")+(b"OK" if allowed else b"DENY")
    ).digest()
    return ContinuityVisibilityGateV0(
        continuity.continuity_epoch,cd,session,ed,posture,roots,relations,detail,allowed,h,False
    )
