"""Composed Strange admission check at a local runtime/launch boundary.

The verifier checks the *exact supplied binary bytes* against trusted native
attestation, the durable canonical 120-second window, and the current
Continuity epoch. All checks are read-only: the returned observation is NOT
a capability or permission to execute a privileged effect.

This Python bootstrap is bypassable by a compromised host or caller. Real
production admission MUST run inside a separate, unbypassable native Trust
Plane, measure the ACTUAL running process and enforce signing policies there.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .strange_durable_continuity_v1 import (
    StrangeDurableContinuityError,
    StrangeDurableContinuityV1,
    StrangeDurableObservationClaimV1,
)
from .strange_native_admission_v1 import (
    StrangeNativeAdmissionError,
    StrangeNativeAttestationV1,
    verify_strange_native_admission_v1,
)


class StrangeRuntimeObservationError(ValueError):
    """The supplied native artifact is not admissible in the current epoch."""


@dataclass(frozen=True, slots=True)
class StrangeRuntimeObservationV1:
    """Nontransferable, unsigned local result; never accept as a credential."""

    observed_epoch: int
    expires_before_seconds: int
    authority: bool = False
    version: int = 1


def _verified_seconds(reader: Callable[[], int]) -> Callable[[], int]:
    """Prevent backward readings *within this admission call*.

    This does not protect against process restart, compromised clocks, or
    rollback of independent hardware time.
    """
    if not callable(reader):
        raise StrangeRuntimeObservationError("trusted seconds reader required")
    previous: int | None = None

    def read() -> int:
        nonlocal previous
        try:
            value = reader()
        except Exception as exc:
            raise StrangeRuntimeObservationError(
                "trusted seconds read failed closed"
            ) from exc
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise StrangeRuntimeObservationError("invalid trusted seconds")
        if previous is not None and value < previous:
            raise StrangeRuntimeObservationError(
                "non-monotonic seconds reading during admission"
            )
        previous = value
        return value

    return read


def require_strange_runtime_observation_v1(
    *,
    continuity_store: StrangeDurableContinuityV1,
    attestation: StrangeNativeAttestationV1,
    native_binary: bytes,
    expected_source_sha256: str,
    deployment_id: str,
    veyra_digest: str,
    mir_fingerprint: str,
    expected_epoch: int,
    expected_start_seconds: int,
    seconds_reader: Callable[[], int],
    attestation_key: bytes,
) -> StrangeRuntimeObservationV1:
    """Check current artifact/tenant/epoch bytes before a LOCAL use attempt.

    A success result must never be cached or used as a signing approval.
    A separate trusted monitor must repeat current-epoch and authorization
    checks at the exact effect boundary to avoid TOCTOU and bypass.
    """
    if not isinstance(continuity_store, StrangeDurableContinuityV1):
        raise StrangeRuntimeObservationError("durable Continuity store required")

    read_seconds = _verified_seconds(seconds_reader)
    try:
        # The local database fixes both epoch and its canonical start. Checking
        # only an epoch number would let a caller substitute a different window.
        initial = continuity_store.require_active_window(
            expected_epoch=expected_epoch,
            expected_start_seconds=expected_start_seconds,
            observed_seconds=read_seconds(),
        )
        verify_strange_native_admission_v1(
            attestation=attestation,
            native_binary=native_binary,
            expected_source_sha256=expected_source_sha256,
            deployment_id=deployment_id,
            veyra_digest=veyra_digest,
            mir_fingerprint=mir_fingerprint,
            continuity=continuity_store.as_continuity_authority(),
            expected_epoch=expected_epoch,
            starts_at_seconds=expected_start_seconds,
            seconds_reader=read_seconds,
            attestation_key=attestation_key,
        )
        # Refuse results that crossed an epoch/window during verification.
        final = continuity_store.require_active_window(
            expected_epoch=expected_epoch,
            expected_start_seconds=expected_start_seconds,
            observed_seconds=read_seconds(),
        )
    except (StrangeDurableContinuityError, StrangeNativeAdmissionError) as exc:
        raise StrangeRuntimeObservationError(
            "native/Continuity admission failed closed"
        ) from exc
    if initial != final:
        raise StrangeRuntimeObservationError(
            "Continuity changed during native admission"
        )
    return StrangeRuntimeObservationV1(
        observed_epoch=final.epoch,
        expires_before_seconds=final.expires_before_seconds,
    )


def consume_strange_runtime_observation_once_v1(
    *,
    continuity_store: StrangeDurableContinuityV1,
    attestation: StrangeNativeAttestationV1,
    native_binary: bytes,
    expected_source_sha256: str,
    deployment_id: str,
    veyra_digest: str,
    mir_fingerprint: str,
    expected_epoch: int,
    expected_start_seconds: int,
    seconds_reader: Callable[[], int],
    attestation_key: bytes,
    request_digest: str,
) -> StrangeDurableObservationClaimV1:
    """Check native evidence then atomically tombstone one LOCAL observation.

    The clock wrapper spans both verification and the SQLite write. The latter
    rechecks epoch/start/time *inside* BEGIN IMMEDIATE before committing a
    unique request digest. A subsequent effect is NOT approved by this result.
    """
    clock = _verified_seconds(seconds_reader)
    require_strange_runtime_observation_v1(
        continuity_store=continuity_store,
        attestation=attestation,
        native_binary=native_binary,
        expected_source_sha256=expected_source_sha256,
        deployment_id=deployment_id,
        veyra_digest=veyra_digest,
        mir_fingerprint=mir_fingerprint,
        expected_epoch=expected_epoch,
        expected_start_seconds=expected_start_seconds,
        seconds_reader=clock,
        attestation_key=attestation_key,
    )
    try:
        return continuity_store.claim_observation_once(
            request_digest=request_digest,
            attestation_digest=attestation.attestation_mac,
            expected_epoch=expected_epoch,
            expected_start_seconds=expected_start_seconds,
            seconds_reader=clock,
        )
    except StrangeDurableContinuityError as exc:
        raise StrangeRuntimeObservationError(
            "durable observation claim failed closed"
        ) from exc
