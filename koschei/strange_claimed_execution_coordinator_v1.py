"""Compose one durable launch attempt with authenticated epoch-native execution.

An opt-in *local* coordinator that creates an unretryable SQLite claim BEFORE
invoking the previously verified Linux runner, then records the reported
outcome. It never rewinds Continuity on failure. It is not an atomic exec
transaction, independent signer, Trust Plane or privileged-effect approval.

The live runner and reconciliation journal are separate existing components;
this module does not modify their low-level entrypoints. A compromised caller
can bypass this coordinator, making it unsuitable as a production gate.
"""
from __future__ import annotations

import hashlib
from typing import Callable

from .mir import MirGraph
from .strange_durable_continuity_v1 import StrangeDurableContinuityV1
from .strange_durable_launch_reconciliation_v1 import (
    StrangeDurableLaunchReconciliationV1,
    StrangeLaunchReconciliationError,
    StrangeLaunchAttemptV1,
)
from .strange_pending_native_build_v1 import (
    PendingStrangeNativeBuildV1,
    StrangePendingNativeBuildError,
)
from .strange_runtime_observation_v1 import (
    StrangeRuntimeObservationError,
    _verified_seconds,
)
from .strange_activated_candidate_launch_v1 import (
    StrangeActivatedCandidateError,
    run_activated_prebuilt_strange_native_v1,
)
from .strange_supervised_native_v1 import StrangeSupervisedRunV1


class StrangeClaimedExecutionError(ValueError):
    """No successful, currently admissible local launch was observed."""


def run_claimed_prebuilt_strange_native_v1(
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
) -> tuple[StrangeSupervisedRunV1, StrangeLaunchAttemptV1]:
    """Claim once, invoke sealed worker, persist result, never auto-retry.

    A success return means only that the local worker returned exit 0 and its
    caller-authenticated *report* was recorded while the same epoch was valid.
    It does NOT permit a secret release or remote privileged operation.
    """
    if not isinstance(mir, MirGraph):
        raise StrangeClaimedExecutionError("sealed canonical MIR required")
    try:
        mir.assert_sealed()
    except ValueError as exc:
        raise StrangeClaimedExecutionError("MIR is not sealed") from exc
    if not isinstance(continuity_store, StrangeDurableContinuityV1):
        raise StrangeClaimedExecutionError("durable Continuity required")
    if not isinstance(pending, PendingStrangeNativeBuildV1):
        raise StrangeClaimedExecutionError("future native artifact required")
    try:
        pending.assert_consistent()
        clock = _verified_seconds(seconds_reader)
    except (StrangePendingNativeBuildError, StrangeRuntimeObservationError) as exc:
        raise StrangeClaimedExecutionError("invalid candidate or trusted clock") from exc

    epoch = pending.pending_projection.target_epoch
    # The reconciliation journal reads the ACTIVATED HMAC-bound handoff,
    # retired-old tombstone, exact candidate digest and live epoch under the
    # same SQLite transaction that reserves the unretryable attempt.
    journal = StrangeDurableLaunchReconciliationV1(continuity_store)
    try:
        journal.claim_once(
            expected_epoch=epoch,
            expected_handoff_mac=expected_handoff_mac,
            expected_native_sha256=pending.native_sha256,
            handoff_key=handoff_key,
            seconds_reader=clock,
        )
    except (StrangeLaunchReconciliationError, ValueError) as exc:
        raise StrangeClaimedExecutionError("no eligible new launch attempt") from exc

    def report(success: bool) -> StrangeLaunchAttemptV1:
        try:
            return journal.record_result(
                epoch=epoch,
                expected_handoff_mac=expected_handoff_mac,
                reported_success=success,
                seconds_reader=clock,
                handoff_key=handoff_key,
            )
        except Exception as exc:
            # Unknown outcome remains durably CLAIMED. It MUST be examined,
            # not automatically retried; never roll back the epoch.
            raise StrangeClaimedExecutionError(
                "unreconciled launch claim; manual investigation required"
            ) from exc

    try:
        run = run_activated_prebuilt_strange_native_v1(
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
    except Exception as exc:
        report(False)
        raise StrangeClaimedExecutionError(
            "native process launch failed; epoch is not rolled back"
        ) from exc

    # A Python return value is not independently trusted process evidence.
    # At minimum reject malformed/spoofed reports before recording success.
    success = (
        type(run) is StrangeSupervisedRunV1
        and run.version == 1
        and run.authority is False
        and type(run.exit_code) is int
        and run.exit_code == 0
        and run.observed_epoch == epoch
        and run.native_sha256 == hashlib.sha256(pending.binary).hexdigest()
    )
    final = report(success)
    if not success:
        raise StrangeClaimedExecutionError(
            "native runner returned a failed or inconsistent observation"
        )
    return run, final
