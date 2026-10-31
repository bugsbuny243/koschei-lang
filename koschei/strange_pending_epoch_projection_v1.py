"""Prepare a *non-authoritative* next-epoch Go source while old epoch lives.

The existing Strange projector rejects an inactive future epoch, preventing
preparation ahead of the 120-second boundary. This builder-only contract
derives the identical scoped source for exactly the NEXT epoch, but produces
a PendingStrangeProjectionV1 that is NOT accepted by the native attestation
issuer and cannot be used as an execution/admission credential.

It requires durable canonical Continuity state, a caller-supplied protected
seed and clock. No HSM, immutable Trust Plane, signer rights, or deployment
cutover is implemented here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from typing import Callable

from .mir import MirGraph
from .mir_go_native import generate_go_mir_native
from .strange_durable_continuity_v1 import (
    StrangeDurableContinuityError,
    StrangeDurableContinuityV1,
)
from .strange_runtime_observation_v1 import (
    StrangeRuntimeObservationError,
    _verified_seconds,
)
from .strange_representation_epoch_v1 import (
    StrangeRepresentationEpochError,
    _CTX,
    _WINDOW_SECONDS,
    _fingerprint,
    _frame,
    _text,
    _seconds,
)


class StrangePendingRepresentationError(ValueError):
    """The next-epoch candidate is invalid, stale, or already active."""


@dataclass(frozen=True, slots=True)
class PendingStrangeProjectionV1:
    """Builder-only metadata; intentionally NOT StrangeEpochProjectionV1."""

    previous_epoch: int
    target_epoch: int
    starts_at_seconds: int
    expires_before_seconds: int
    source_sha256: str
    authority: bool = False
    version: int = 1


def project_next_strange_epoch_go_v1(
    mir: MirGraph,
    *,
    continuity_store: StrangeDurableContinuityV1,
    trust_plane_seed: bytes,
    expected_current_epoch: int,
    expected_current_start_seconds: int,
    seconds_reader: Callable[[], int],
    deployment_id: str,
    veyra_digest: str,
) -> tuple[str, PendingStrangeProjectionV1]:
    """Render an inactive NEXT-epoch source, never a runtime grant.

    A candidate built at T=119 is only a candidate. Before use after
    T=120, the trusted builder MUST recheck its exact source and binary
    identity against the activated Continuity head and attestation policy.
    """
    if not isinstance(mir, MirGraph):
        raise StrangePendingRepresentationError("sealed canonical MIR required")
    try:
        mir.assert_sealed()
    except ValueError as exc:
        raise StrangePendingRepresentationError("canonical MIR is unsealed") from exc
    if not isinstance(continuity_store, StrangeDurableContinuityV1):
        raise StrangePendingRepresentationError("durable Continuity required")
    if not isinstance(trust_plane_seed, bytes) or len(trust_plane_seed) < 32:
        raise StrangePendingRepresentationError("private Trust Plane seed requires 256 bits")
    if (
        not isinstance(expected_current_epoch, int)
        or isinstance(expected_current_epoch, bool)
        or not 1 <= expected_current_epoch < 2**63 - 1
        or not isinstance(expected_current_start_seconds, int)
        or isinstance(expected_current_start_seconds, bool)
        or not 0 <= expected_current_start_seconds < 2**63 - 2 * _WINDOW_SECONDS
    ):
        raise StrangePendingRepresentationError("invalid current epoch/window")
    target_epoch = expected_current_epoch + 1
    next_start = expected_current_start_seconds + _WINDOW_SECONDS
    clock = _verified_seconds(clock)
    try:
        before = continuity_store.require_active_window(
            expected_epoch=expected_current_epoch,
            expected_start_seconds=expected_current_start_seconds,
            observed_seconds=_seconds(clock),
        )
        fields = (
            _text(deployment_id, "deployment identity"),
            _fingerprint(veyra_digest, "Veyra digest"),
            _fingerprint(mir.fingerprint, "MIR fingerprint"),
            target_epoch.to_bytes(8, "big"),
            next_start.to_bytes(8, "big"),
            _WINDOW_SECONDS.to_bytes(4, "big"),
        )
        # Use the *same* derivation as the active Strange epoch projector.
        # No public clock value is used as a secret.
        seed = hmac.new(
            trust_plane_seed,
            _CTX + b"".join(_frame(item) for item in fields),
            hashlib.sha256,
        ).digest()
        source = generate_go_mir_native(mir, representation_seed=seed)
        after = continuity_store.require_active_window(
            expected_epoch=expected_current_epoch,
            expected_start_seconds=expected_current_start_seconds,
            observed_seconds=_seconds(clock),
        )
    except (
        StrangeDurableContinuityError,
        StrangeRepresentationEpochError,
        StrangeRuntimeObservationError,
        ValueError,
    ) as exc:
        raise StrangePendingRepresentationError(
            "next-epoch preparation requires unchanged, current Continuity"
        ) from exc
    if before != after:
        raise StrangePendingRepresentationError("Continuity changed during source preparation")
    return source, PendingStrangeProjectionV1(
        previous_epoch=expected_current_epoch,
        target_epoch=target_epoch,
        starts_at_seconds=next_start,
        expires_before_seconds=next_start + _WINDOW_SECONDS,
        source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
    )
