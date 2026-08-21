"""Epoch rebirth protocol for contained Koschei Universe states.

Containment is terminal inside one epoch. Re-entry is not a state flip: it creates
a fresh epoch with fresh lifecycle evidence and deliberately carries no runtime
authority forward. The activation plan identity remains stable while the lifecycle
identity changes.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .universe_state_machine_v1 import (
    SigilLifecycle,
    SigilState,
    UniverseState,
    UniverseStateError,
)

_CTX = b"koschei.universe-rebirth/v1\x00"


class UniverseRebirthError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RebirthReceipt:
    previous_state_digest: str
    activation_plan_digest: str
    previous_epoch: int
    next_epoch: int
    cause_evidence_digest: str
    fresh_state_digest: str
    digest: str


def _state_digest(plan_digest: str, rows: tuple[SigilLifecycle, ...]) -> str:
    parts = [f"plan={plan_digest}"]
    for row in rows:
        parts.append(
            f"sigil={row.sigil}|state={row.state.value}|epoch={row.epoch}|evidence={row.evidence_digest}"
        )
    return hashlib.sha256(
        b"koschei.universe-state-machine/v1\x00" + "\n".join(parts).encode("utf-8")
    ).hexdigest()


def _receipt_digest(
    previous_state_digest: str,
    activation_plan_digest: str,
    previous_epoch: int,
    next_epoch: int,
    cause_evidence_digest: str,
    fresh_state_digest: str,
) -> str:
    payload = "\n".join(
        (
            f"previous={previous_state_digest}",
            f"plan={activation_plan_digest}",
            f"previous_epoch={previous_epoch}",
            f"next_epoch={next_epoch}",
            f"cause={cause_evidence_digest}",
            f"fresh={fresh_state_digest}",
        )
    ).encode("utf-8")
    return hashlib.sha256(_CTX + payload).hexdigest()


def rebirth_contained_universe(
    state: UniverseState,
    *,
    cause_evidence_digest: str,
) -> tuple[UniverseState, RebirthReceipt]:
    """Create a new inactive epoch from a fully contained universe.

    No sigil state, authority token, prior transition evidence or active bit is
    inherited. Only the canonical activation-plan identity and sigil membership
    survive. This prevents recovery from silently resurrecting old authority.
    """

    if not cause_evidence_digest:
        raise UniverseRebirthError("rebirth requires containment/recovery evidence")
    if not state.sigils:
        raise UniverseRebirthError("cannot rebirth an empty universe")
    if any(row.state is not SigilState.CONTAINED for row in state.sigils):
        raise UniverseRebirthError("rebirth requires every sigil to be contained")

    epochs = {row.epoch for row in state.sigils}
    if len(epochs) != 1:
        raise UniverseRebirthError("split-epoch universe cannot be reborn")
    previous_epoch = next(iter(epochs))
    if previous_epoch < 1:
        raise UniverseRebirthError("invalid previous universe epoch")
    next_epoch = previous_epoch + 1

    fresh_rows = tuple(
        SigilLifecycle(
            sigil=row.sigil,
            state=SigilState.INACTIVE,
            epoch=next_epoch,
            evidence_digest="",
        )
        for row in state.sigils
    )
    fresh_digest = _state_digest(state.activation_plan_digest, fresh_rows)
    fresh = UniverseState(
        activation_plan_digest=state.activation_plan_digest,
        sigils=fresh_rows,
        digest=fresh_digest,
    )
    receipt = RebirthReceipt(
        previous_state_digest=state.digest,
        activation_plan_digest=state.activation_plan_digest,
        previous_epoch=previous_epoch,
        next_epoch=next_epoch,
        cause_evidence_digest=cause_evidence_digest,
        fresh_state_digest=fresh.digest,
        digest=_receipt_digest(
            state.digest,
            state.activation_plan_digest,
            previous_epoch,
            next_epoch,
            cause_evidence_digest,
            fresh.digest,
        ),
    )
    return fresh, receipt


def require_rebirth_receipt(
    previous: UniverseState,
    fresh: UniverseState,
    receipt: RebirthReceipt,
) -> None:
    if receipt.previous_state_digest != previous.digest:
        raise UniverseRebirthError("rebirth receipt previous-state mismatch")
    if receipt.activation_plan_digest != previous.activation_plan_digest:
        raise UniverseRebirthError("rebirth receipt plan mismatch")
    if fresh.activation_plan_digest != previous.activation_plan_digest:
        raise UniverseRebirthError("rebirth changed activation-plan identity")
    if receipt.fresh_state_digest != fresh.digest:
        raise UniverseRebirthError("rebirth receipt fresh-state mismatch")
    if receipt.next_epoch != receipt.previous_epoch + 1:
        raise UniverseRebirthError("rebirth epoch is not monotonic")
    expected = _receipt_digest(
        receipt.previous_state_digest,
        receipt.activation_plan_digest,
        receipt.previous_epoch,
        receipt.next_epoch,
        receipt.cause_evidence_digest,
        receipt.fresh_state_digest,
    )
    if expected != receipt.digest:
        raise UniverseRebirthError("rebirth receipt digest mismatch")
    if any(row.state is not SigilState.CONTAINED for row in previous.sigils):
        raise UniverseRebirthError("previous universe was not fully contained")
    if any(row.state is not SigilState.INACTIVE for row in fresh.sigils):
        raise UniverseRebirthError("fresh universe did not restart inactive")
    if any(row.epoch != receipt.next_epoch for row in fresh.sigils):
        raise UniverseRebirthError("fresh universe epoch mismatch")
