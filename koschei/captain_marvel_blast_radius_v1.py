"""Captain Marvel Blast Radius v1.

Containment physics for cross-reality propagation. An incident receives an
explicit propagation budget; containment can only preserve or reduce that
budget and cannot mint new destinations or authority.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib

_CTX=b"koschei.captain-marvel-blast-radius/v1\x00"

class BlastRadiusError(ValueError): pass

@dataclass(frozen=True, slots=True)
class BlastRadiusBudgetV1:
    origin_reality: str
    allowed_destinations: frozenset[str]
    max_hops: int
    max_effects: int
    budget_digest: bytes

@dataclass(frozen=True, slots=True)
class PropagationVerdictV1:
    allowed: bool
    reason: str
    remaining_hops: int
    remaining_effects: int
    verdict_digest: bytes
    authority: bool=False


def issue_blast_radius_budget_v1(*, origin_reality: str, allowed_destinations: frozenset[str],
    max_hops: int, max_effects: int) -> BlastRadiusBudgetV1:
    if not origin_reality or max_hops<0 or max_effects<0:
        raise BlastRadiusError("invalid blast-radius budget")
    if origin_reality in allowed_destinations:
        raise BlastRadiusError("origin cannot be a propagation destination")
    h=hashlib.sha3_256(_CTX+b"budget\x00"+origin_reality.encode())
    for d in sorted(allowed_destinations):
        if not d: raise BlastRadiusError("destination must be explicit")
        h.update(b"\x00"+d.encode())
    h.update(max_hops.to_bytes(8,"big")+max_effects.to_bytes(8,"big"))
    return BlastRadiusBudgetV1(origin_reality,allowed_destinations,max_hops,max_effects,h.digest())


def evaluate_propagation_v1(budget: BlastRadiusBudgetV1, *, destination: str,
    hops_used: int, effects_used: int) -> PropagationVerdictV1:
    if not isinstance(budget,BlastRadiusBudgetV1): raise BlastRadiusError("canonical budget required")
    if hops_used<0 or effects_used<0: raise BlastRadiusError("usage cannot be negative")
    allowed=True; reason="within-blast-radius"
    if destination not in budget.allowed_destinations:
        allowed=False; reason="destination-outside-blast-radius"
    elif hops_used>=budget.max_hops:
        allowed=False; reason="hop-budget-exhausted"
    elif effects_used>=budget.max_effects:
        allowed=False; reason="effect-budget-exhausted"
    rh=max(0,budget.max_hops-hops_used-(1 if allowed else 0))
    re=max(0,budget.max_effects-effects_used-(1 if allowed else 0))
    body=b"\x00".join((budget.budget_digest,destination.encode(),str(hops_used).encode(),str(effects_used).encode(),reason.encode(),b"1" if allowed else b"0"))
    d=hashlib.sha3_256(_CTX+b"verdict\x00"+body).digest()
    return PropagationVerdictV1(allowed,reason,rh,re,d,False)
