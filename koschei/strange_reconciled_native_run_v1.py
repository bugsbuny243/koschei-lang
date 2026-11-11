"""Bind an activated epoch's single local launch claim to a supervised worker.

Opt-in local orchestration driver. The durable SQLite claim is created BEFORE
calling the activated, sealed native worker. A successful run is returned
ONLY after the journal reports REPORTED_OK for the same still-live epoch.
A failed run is recorded REPORTED_FAILED where possible. Unknown outcomes
remain CLAIMED on crash or failed reconciliation: NEVER auto-retry or roll
Continuity back.

This is NOT OS-atomic fork/exec, process attestation, signer authorization,
a distributed lock, or an unbypassable production Trust Plane.
"""
from __future__ import annotations

from typing import Callable

from .mir import MirGraph
from .strange_durable_continuity_v1 import StrangeDurableContinuityV1
from .strange_durable_launch_reconciliation_v1 import (
    StrangeDurableLaunchReconciliationV1,
    StrangeLaunchReconciliationError,
)
from .strange_pending_native_build_v1 import PendingStrangeNativeBuildV1
from .strange_runtime_observation_v1 import _verified_seconds, StrangeRuntimeObservationError
from .strange_activated_candidate_launch_v1 import (
    StrangeActivatedCandidateError,
    run_activated_prebuilt_strange_native_v1,
)
from .strange_supervised_native_v1 import StrangeSupervisedRunV1


class StrangeReconciledNativeError(ValueError):
    """Launch rejected or could not be unambiguously reconciled."""


def run_reconciled_prebuilt_strange_native_v1(
    mir: MirGraph,
    *,
    continuity_store: StrangeDurableContinuityV1,
    pending: PendingStrangeNativeBuildV1,
    handoff_key: bytes,
    expected_handoff_mac: str,
    trust_plane_seed: bytes,
    seconds_reader: Callable[[], int],
    deployment_id: str,
    veyra_digest: str,
    attestation_key: bytes,
    expected_go_sha256: str,
    run_timeout_seconds: int = 10,
    poll_interval_seconds: float = 0.05,
) -> StrangeSupervisedRunV1:
    """Reserve once, launch actual sealed bytes, and persist outcome.

    This driver intentionally cannot tell whether a crash occurred before or
    after OS launch. An unresolved CLAIMED record must be investigated by an
    operator; do not treat that record as permission to launch again.
    """
    if not isinstance(continuity_store, StrangeDurableContinuityV1):
        raise StrangeReconciledNativeError("durable Continuity store required")
    if not isinstance(pending, PendingStrangeNativeBuildV1):
        raise StrangeReconciledNativeError("typed pending native binary required")
    try:
        clock = _verified_seconds(seconds_reader)
        pending.assert_consistent()
    except (StrangeRuntimeObservationError, ValueError) as exc:
        raise StrangeReconciledNativeError("invalid launch candidate or time reader") from exc

    # The claim checks exact HMAC-bound activated candidate, old-epoch
    # retirement and fresh current Continuity time under BEGIN IMMEDIATE.
    journal = StrangeDurableLaunchReconciliationV1(continuity_store)
    next_epoch = pending.pending_projection.target_epoch
    try:
        journal.claim_once(
            expected_epoch=next_epoch,
            expected_handoff_mac=expected_handoff_mac,
            expected_native_sha256=pending.native_sha256,
            handoff_key=handoff_key,
            seconds_reader=clock,
        )
    except Exception as exc:
        # SQLite I/O/lock failures are also hard denials. A launch must never
        # begin unless its one-time claim has definitely committed.
        raise StrangeReconciledNativeError(
            "launch claim not confirmed; native worker was not started"
        ) from exc

    runner_error: Exception | None = None
    result: StrangeSupervisedRunV1 | None = None
    try:
        result = run_activated_prebuilt_strange_native_v1(
            mir,
            continuity_store=continuity_store,
            pending=pending,
            handoff_key=handoff_key,
            expected_handoff_mac=expected_handoff_mac,
            trust_plane_seed=trust_plane_seed,
            seconds_reader=clock,
            deployment_id=deployment_id,
            veyra_digest=veyra_digest,
            attestation_key=attestation_key,
            expected_go_sha256=expected_go_sha256,
            run_timeout_seconds=run_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        if result.authority is not False or result.observed_epoch != next_epoch:
            raise StrangeReconciledNativeError("runner result is not a current non-authoritative observation")
        if result.native_sha256 != pending.native_sha256:
            raise StrangeReconciledNativeError("runner observed unexpected native binary")
        if result.exit_code != 0:
            raise StrangeReconciledNativeError("native worker returned nonzero exit code")
    except Exception as exc:
        runner_error = exc

    # The report is itself read-only telemetry: even REPORTED_OK does not
    # authorize a wallet, Khar/Sathra or other privileged operation.
    try:
        reported = journal.record_result(
            epoch=next_epoch,
            expected_handoff_mac=expected_handoff_mac,
            reported_success=runner_error is None,
            seconds_reader=clock,
            handoff_key=handoff_key,
        )
    except Exception as exc:
        # A late positive result or missing clock cannot count as success.
        # Leave the CLAIMED state unresolved; no automatic replay.
        raise StrangeReconciledNativeError(
            "worker result unresolved; manual investigation required, do not retry"
        ) from exc

    if runner_error is not None or reported.state != "REPORTED_OK" or result is None:
        raise StrangeReconciledNativeError(
            "worker failed, attempt recorded; next eligible epoch required"
        ) from runner_error
    return result
