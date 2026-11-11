"""Lifecycle state machine for Koschei Universe sigils.

A sigil is not active merely because it appears in a plan. It must move through
explicit preparation and sealing before activation. Containment is terminal for
normal operation and can only be left through a new activation epoch.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from typing import Iterable, Mapping

from .universe_activation_engine_v1 import UniverseActivationPlan, compile_activation_plan

_CTX = b"koschei.universe-state-machine/v1\x00"


class UniverseStateError(ValueError):
    pass


class SigilState(str, Enum):
    INACTIVE = "inactive"
    PREPARED = "prepared"
    SEALED = "sealed"
    ACTIVE = "active"
    CONTAINED = "contained"


_ALLOWED = {
    SigilState.INACTIVE: frozenset({SigilState.PREPARED}),
    SigilState.PREPARED: frozenset({SigilState.SEALED, SigilState.CONTAINED}),
    SigilState.SEALED: frozenset({SigilState.ACTIVE, SigilState.CONTAINED}),
    SigilState.ACTIVE: frozenset({SigilState.CONTAINED}),
    SigilState.CONTAINED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class SigilLifecycle:
    sigil: str
    state: SigilState
    epoch: int
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class UniverseState:
    activation_plan_digest: str
    sigils: tuple[SigilLifecycle, ...]
    digest: str


def _digest(plan_digest: str, rows: Iterable[SigilLifecycle]) -> str:
    parts = [f"plan={plan_digest}"]
    for row in rows:
        parts.append(f"sigil={row.sigil}|state={row.state.value}|epoch={row.epoch}|evidence={row.evidence_digest}")
    return hashlib.sha256(_CTX + "\n".join(parts).encode("utf-8")).hexdigest()


def initial_universe_state(sigils: Iterable[str], *, epoch: int = 1) -> UniverseState:
    if epoch < 1:
        raise UniverseStateError("universe epoch must be positive")
    plan = compile_activation_plan(tuple(sigils))
    rows = tuple(
        SigilLifecycle(sigil=sigil, state=SigilState.INACTIVE, epoch=epoch, evidence_digest="")
        for sigil in plan.composed.base.sigils
    )
    return UniverseState(plan.digest, rows, _digest(plan.digest, rows))


def transition_sigil(
    state: UniverseState,
    sigil: str,
    target: SigilState,
    *,
    evidence_digest: str,
) -> UniverseState:
    if not evidence_digest:
        raise UniverseStateError("state transition requires evidence digest")
    rows = list(state.sigils)
    index = next((i for i, row in enumerate(rows) if row.sigil == sigil), None)
    if index is None:
        raise UniverseStateError(f"sigil is not part of this universe plan: {sigil}")
    current = rows[index]
    if target not in _ALLOWED[current.state]:
        raise UniverseStateError(
            f"non-canonical sigil transition: {sigil} {current.state.value}->{target.value}"
        )

    # Genesis is the first trust anchor. No non-ka sigil may become ACTIVE while
    # ka is present but not ACTIVE. This prevents half-booted universes.
    if target is SigilState.ACTIVE and sigil != "ka":
        ka = next((row for row in rows if row.sigil == "ka"), None)
        if ka is not None and ka.state is not SigilState.ACTIVE:
            raise UniverseStateError("ka must be active before another sigil can activate")

    rows[index] = SigilLifecycle(
        sigil=sigil,
        state=target,
        epoch=current.epoch,
        evidence_digest=evidence_digest,
    )
    frozen = tuple(rows)
    return UniverseState(
        activation_plan_digest=state.activation_plan_digest,
        sigils=frozen,
        digest=_digest(state.activation_plan_digest, frozen),
    )


def require_fully_active(state: UniverseState) -> None:
    inactive = [row.sigil for row in state.sigils if row.state is not SigilState.ACTIVE]
    if inactive:
        raise UniverseStateError(
            "universe is not fully active: " + ",".join(inactive)
        )


def contain_universe(state: UniverseState, *, evidence_digest: str) -> UniverseState:
    if not evidence_digest:
        raise UniverseStateError("containment requires evidence digest")
    rows = tuple(
        row if row.state is SigilState.CONTAINED else SigilLifecycle(
            sigil=row.sigil,
            state=SigilState.CONTAINED,
            epoch=row.epoch,
            evidence_digest=evidence_digest,
        )
        for row in state.sigils
    )
    return UniverseState(state.activation_plan_digest, rows, _digest(state.activation_plan_digest, rows))
