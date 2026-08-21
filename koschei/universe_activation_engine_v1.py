"""Deterministic activation engine for composed Koschei Universe plans.

A universe plan is not executable merely because its modules are known.  This
engine converts sigil obligations and emergent interaction obligations into an
ordered, fail-closed activation schedule with explicit dependency edges.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from .universe_interactions_v1 import ComposedUniversePlan, compose_universe

_CTX = b"koschei.universe-activation-engine/v1\x00"


class UniverseActivationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ActivationStep:
    step_id: str
    phase: str
    obligation: str
    requires: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UniverseActivationPlan:
    composed: ComposedUniversePlan
    steps: tuple[ActivationStep, ...]
    digest: str


_PHASE_ORDER = (
    "genesis",
    "authority",
    "evidence",
    "containment",
    "visibility",
    "conservation",
)
_PHASE_RANK = {name: index for index, name in enumerate(_PHASE_ORDER)}


def _phase_for(obligation: str) -> str:
    if any(token in obligation for token in ("identity", "genesis", "integrity", "lineage")):
        return "genesis"
    if any(token in obligation for token in ("authority", "authorization", "effect-contract", "least-authority")):
        return "authority"
    if any(token in obligation for token in ("evidence", "attest", "observation")):
        return "evidence"
    if any(token in obligation for token in ("recovery", "containment", "fence", "exactly-once", "commit", "abort")):
        return "containment"
    if any(token in obligation for token in ("visibility", "knowledge", "compartment", "observer")):
        return "visibility"
    if "conservation" in obligation:
        return "conservation"
    # Unknown obligations are not guessed into a permissive phase.
    raise UniverseActivationError(f"unclassified universe obligation: {obligation}")


def _step_id(phase: str, obligation: str) -> str:
    payload = f"{phase}\x00{obligation}".encode("utf-8")
    return f"{phase}:{hashlib.sha256(_CTX + payload).hexdigest()[:16]}"


def compile_activation_plan(sigils: Iterable[str]) -> UniverseActivationPlan:
    composed = compose_universe(tuple(sigils))
    obligations = tuple(sorted(set(composed.base.obligations) | set(composed.emergent_obligations)))
    classified = [(obligation, _phase_for(obligation)) for obligation in obligations]
    classified.sort(key=lambda item: (_PHASE_RANK[item[1]], item[0]))

    phase_last: dict[str, str] = {}
    steps: list[ActivationStep] = []
    for obligation, phase in classified:
        rank = _PHASE_RANK[phase]
        dependencies: list[str] = []
        # Within a phase, preserve canonical serial order.
        if phase in phase_last:
            dependencies.append(phase_last[phase])
        # Every later phase depends on the final step of every earlier active phase.
        for prior in _PHASE_ORDER[:rank]:
            if prior in phase_last:
                dependencies.append(phase_last[prior])

        step = ActivationStep(
            step_id=_step_id(phase, obligation),
            phase=phase,
            obligation=obligation,
            requires=tuple(dict.fromkeys(dependencies)),
        )
        steps.append(step)
        phase_last[phase] = step.step_id

    if not steps:
        raise UniverseActivationError("universe activation plan has no executable obligations")

    # Conservation must be terminal when the full-universe rule is active.
    conservation_steps = [step for step in steps if step.phase == "conservation"]
    if conservation_steps and steps[-1].phase != "conservation":
        raise UniverseActivationError("whole-universe conservation must seal the activation plan")

    digest = hashlib.sha256(_CTX + "\n".join(
        [f"composed={composed.digest}"]
        + [
            f"step={step.step_id}|{step.phase}|{step.obligation}|{','.join(step.requires)}"
            for step in steps
        ]
    ).encode("utf-8")).hexdigest()

    return UniverseActivationPlan(composed=composed, steps=tuple(steps), digest=digest)
