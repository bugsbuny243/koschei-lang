"""Epoch-bound sigil tokens for the Koschei Universe.

A sigil becoming active does not create an eternal privilege marker.  This module
binds activation tokens to the universe plan, sigil, lifecycle evidence and epoch.
Tokens from a contained or previous epoch are cryptographically stale and cannot
be reused after rebirth.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .universe_state_machine_v1 import SigilState, UniverseState

_CTX = b"koschei.universe-epoch-token/v1\x00"


class UniverseEpochTokenError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SigilEpochToken:
    sigil: str
    epoch: int
    activation_plan_digest: str
    lifecycle_evidence_digest: str
    state_digest: str
    token_digest: str


def _digest(
    sigil: str,
    epoch: int,
    activation_plan_digest: str,
    lifecycle_evidence_digest: str,
    state_digest: str,
) -> str:
    payload = "\n".join(
        (
            f"sigil={sigil}",
            f"epoch={epoch}",
            f"plan={activation_plan_digest}",
            f"evidence={lifecycle_evidence_digest}",
            f"state={state_digest}",
        )
    ).encode("utf-8")
    return hashlib.sha256(_CTX + payload).hexdigest()


def mint_sigil_epoch_token(state: UniverseState, sigil: str) -> SigilEpochToken:
    row = next((item for item in state.sigils if item.sigil == sigil), None)
    if row is None:
        raise UniverseEpochTokenError(f"sigil is not in universe plan: {sigil}")
    if row.state is not SigilState.ACTIVE:
        raise UniverseEpochTokenError("sigil epoch token requires active lifecycle state")
    if not row.evidence_digest:
        raise UniverseEpochTokenError("active sigil is missing lifecycle evidence")
    if row.epoch < 1:
        raise UniverseEpochTokenError("invalid sigil epoch")

    token_digest = _digest(
        sigil,
        row.epoch,
        state.activation_plan_digest,
        row.evidence_digest,
        state.digest,
    )
    return SigilEpochToken(
        sigil=sigil,
        epoch=row.epoch,
        activation_plan_digest=state.activation_plan_digest,
        lifecycle_evidence_digest=row.evidence_digest,
        state_digest=state.digest,
        token_digest=token_digest,
    )


def require_current_sigil_token(
    state: UniverseState,
    token: SigilEpochToken,
    *,
    expected_sigil: str | None = None,
) -> None:
    if expected_sigil is not None and token.sigil != expected_sigil:
        raise UniverseEpochTokenError("sigil token subject mismatch")
    if token.activation_plan_digest != state.activation_plan_digest:
        raise UniverseEpochTokenError("sigil token activation-plan mismatch")

    row = next((item for item in state.sigils if item.sigil == token.sigil), None)
    if row is None:
        raise UniverseEpochTokenError("sigil token refers to unknown sigil")
    if row.state is not SigilState.ACTIVE:
        raise UniverseEpochTokenError("sigil token cannot authorize non-active state")
    if row.epoch != token.epoch:
        raise UniverseEpochTokenError("stale sigil token epoch")
    if row.evidence_digest != token.lifecycle_evidence_digest:
        raise UniverseEpochTokenError("sigil token lifecycle evidence mismatch")
    if token.state_digest != state.digest:
        raise UniverseEpochTokenError("sigil token state snapshot is stale")

    expected = _digest(
        token.sigil,
        token.epoch,
        token.activation_plan_digest,
        token.lifecycle_evidence_digest,
        token.state_digest,
    )
    if expected != token.token_digest:
        raise UniverseEpochTokenError("sigil token digest mismatch")
