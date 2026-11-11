"""Catastrophic fail-closed containment profile for Koschei Universe v1.

"Nuclear" here is strictly defensive terminology: it never attacks an external
party.  It describes the most severe local response available to Koschei when
continuing execution would be less safe than sacrificing availability.

The profile composes existing Universe and runtime invariants into one sealed
catastrophic-containment receipt.  A caller is expected to execute the listed
local defensive actions (revoke/expire authority, tombstone the epoch, isolate
privileged effects, preserve evidence, rotate compartments, and zeroize
configured ephemeral secret handles) and prove completion before rebirth.

This module does not delete arbitrary user data and does not implement offensive
countermeasures.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from .universe_state_machine_v1 import UniverseState, contain_universe

_CTX = b"koschei.universe-nuclear-containment/v1\x00"


class NuclearContainmentError(ValueError):
    pass


_REQUIRED_ACTIONS = (
    "freeze-privileged-effects",
    "revoke-active-authority",
    "tombstone-current-epoch",
    "isolate-execution-boundaries",
    "preserve-forensic-evidence",
    "rotate-visible-compartments",
    "zeroize-ephemeral-secret-handles",
    "require-manual-or-independent-rebirth-proof",
)


@dataclass(frozen=True, slots=True)
class NuclearContainmentReceipt:
    previous_state_digest: str
    contained_state_digest: str
    epoch: int
    cause_evidence_digest: str
    completed_actions: tuple[str, ...]
    external_effects_attempted: bool
    digest: str
    version: int = 1

    def assert_sealed(self) -> None:
        if self.epoch < 1:
            raise NuclearContainmentError("nuclear containment epoch must be positive")
        if not self.cause_evidence_digest:
            raise NuclearContainmentError("nuclear containment requires cause evidence")
        if self.external_effects_attempted:
            raise NuclearContainmentError(
                "nuclear containment must never perform retaliatory/external effects"
            )
        if tuple(self.completed_actions) != _REQUIRED_ACTIONS:
            raise NuclearContainmentError("nuclear containment action set incomplete")
        expected = _receipt_digest(
            self.previous_state_digest,
            self.contained_state_digest,
            self.epoch,
            self.cause_evidence_digest,
            self.completed_actions,
            self.external_effects_attempted,
        )
        if expected != self.digest:
            raise NuclearContainmentError("nuclear containment receipt seal mismatch")


def required_nuclear_actions() -> tuple[str, ...]:
    return _REQUIRED_ACTIONS


def _receipt_digest(
    previous_state_digest: str,
    contained_state_digest: str,
    epoch: int,
    cause_evidence_digest: str,
    completed_actions: Iterable[str],
    external_effects_attempted: bool,
) -> str:
    payload = "\n".join(
        (
            f"previous={previous_state_digest}",
            f"contained={contained_state_digest}",
            f"epoch={epoch}",
            f"cause={cause_evidence_digest}",
            "actions=" + ",".join(completed_actions),
            f"external-effects={int(external_effects_attempted)}",
        )
    ).encode("utf-8")
    return hashlib.sha256(_CTX + payload).hexdigest()


def enter_nuclear_containment(
    state: UniverseState,
    *,
    cause_evidence_digest: str,
) -> tuple[UniverseState, NuclearContainmentReceipt]:
    """Enter the maximum defensive local-containment profile.

    The Universe is first forced into ordinary terminal containment.  The receipt
    then requires the caller/runtime to treat every privileged boundary as frozen
    and the current epoch as dead until an independently proven rebirth occurs.
    """

    if not cause_evidence_digest:
        raise NuclearContainmentError("nuclear containment requires cause evidence")
    if not state.sigils:
        raise NuclearContainmentError("cannot contain an empty universe")

    epochs = {row.epoch for row in state.sigils}
    if len(epochs) != 1:
        raise NuclearContainmentError("split-epoch universe cannot enter nuclear containment")
    epoch = next(iter(epochs))

    contained = contain_universe(state, evidence_digest=cause_evidence_digest)
    receipt = NuclearContainmentReceipt(
        previous_state_digest=state.digest,
        contained_state_digest=contained.digest,
        epoch=epoch,
        cause_evidence_digest=cause_evidence_digest,
        completed_actions=_REQUIRED_ACTIONS,
        external_effects_attempted=False,
        digest="",
    )
    object.__setattr__(
        receipt,
        "digest",
        _receipt_digest(
            receipt.previous_state_digest,
            receipt.contained_state_digest,
            receipt.epoch,
            receipt.cause_evidence_digest,
            receipt.completed_actions,
            receipt.external_effects_attempted,
        ),
    )
    receipt.assert_sealed()
    return contained, receipt


def require_nuclear_containment(
    previous: UniverseState,
    contained: UniverseState,
    receipt: NuclearContainmentReceipt,
) -> None:
    receipt.assert_sealed()
    if receipt.previous_state_digest != previous.digest:
        raise NuclearContainmentError("nuclear receipt previous-state mismatch")
    if receipt.contained_state_digest != contained.digest:
        raise NuclearContainmentError("nuclear receipt contained-state mismatch")
    if any(row.state.value != "contained" for row in contained.sigils):
        raise NuclearContainmentError("nuclear containment did not contain every sigil")
    if any(row.epoch != receipt.epoch for row in contained.sigils):
        raise NuclearContainmentError("nuclear containment epoch mismatch")
