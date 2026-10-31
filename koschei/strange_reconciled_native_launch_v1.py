"""Opt-in local launch attempt accounting around activated sealed native execution.

The durable at-most-once CLAIMED record is written before requesting the
existing activated native launch. Success and failure are merely runner-reported
outcomes and do NOT grant trusted execution or effect authority. If reporting
fails or the process crashes, CLAIMED remains for operator reconciliation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .mir import MirGraph
from .strange_durable_continuity_v1 import StrangeDurableContinuityV1
from .strange_pending_native_build_v1 import (
    PendingStrangeNativeBuildV1,
    StrangePendingNativeBuildError,
)
from .strange_activated_candidate_launch_v1 import (
    StrangeActivatedCandidateError,
    run_activated_prebuilt_strange_native_v1,
)
from .strange_durable_launch_reconciliation_v1 import (
    StrangeDurableLaunchReconciliationV1,
    StrangeLaunchAttemptV1,
    StrangeLaunchReconciliationError,
)
from .strange_runtime_observation_v1 import (
    StrangeRuntimeObservationError,
    _verified_seconds,
)
from .strange_supervised_native_v1 import StrangeSupervisedRunV1


class StrangeReconciledNativeLaunchError(ValueError):
    """Cannot safely claim, start, or report this local native attempt."""


@dataclass(frozen=True, slots=True)
class StrangeReconciledNativeResultV1:
    """Unsigned local outcome only; NOT a signer authorization token."""

    run: StrangeSupervisedRunV1 = field(repr=False)
    report: StrangeLaunchAttemptV1
    authority: bool = False
    version: int = 1


def run_reconciled_activated_native_v1(
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
) -> StrangeReconciledNativeResultV1:
    """Journal exactly one local launch request, then report observed outcome.

    IMPORTANT: This records the request; it does not lock or fence the
    subprocess at kernel/Trust Plane level. Other entry points can bypass
    it. Manual investigation is required for a CLAIMED record without a
    result. The previous epoch is NEVER restored on an error.
    """
    if not isinstance(continuity_store, StrangeDurableContinuityV1):
        raise StrangeReconciledNativeLaunchError("durable Continuity required")
    if not isinstance(pending, PendingStrangeNativeBuildV1):
        raise StrangeReconciledNativeLaunchError("typed prebuilt native candidate required")
    if not isinstance(mir, MirGraph):
        raise StrangeReconciledNativeLaunchError("sealed canonical MIR required")
    try:
        mir.assert_sealed()
        pending.assert_consistent()
        clock = _verified_seconds(seconds_reader)
    except (
        ValueError, StrangePendingNativeBuildError,
        StrangeRuntimeObservationError,
    ) as exc:
        raise StrangeReconciledNativeLaunchError("invalid prelaunch identity or time") from exc

    journal = StrangeDurableLaunchReconciliationV1(continuity_store)
    epoch = pending.pending_projection.target_epoch
    try:
        claim = journal.claim_once(
            expected_epoch=epoch,
            expected_handoff_mac=expected_handoff_mac,
            expected_native_sha256=pending.native_sha256,
            handoff_key=handoff_key,
            seconds_reader=clock,
        )
    except (StrangeLaunchReconciliationError, ValueError) as exc:
        raise StrangeReconciledNativeLaunchError(
            "launch claim rejected; repeat execution forbidden"
        ) from exc

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
    except StrangeActivatedCandidateError as exc:
        # Even a failed launch permanently consumes this epoch's attempt.
        # If the reporting transaction fails, CLAIMED is left untouched.
        try:
            journal.record_result(
                epoch=epoch,
                expected_handoff_mac=claim.handoff_mac,
                reported_success=False,
                seconds_reader=clock,
                handoff_key=handoff_key,
            )
        except (StrangeLaunchReconciliationError, ValueError) as report_exc:
            raise StrangeReconciledNativeLaunchError(
                "launch failed; outcome unresolved and operator reconciliation required"
            ) from report_exc
        raise StrangeReconciledNativeLaunchError(
            "activated native launch failed; failure durably reported"
        ) from exc

    # A nonzero exit is a failure, not a success despite a valid native image.
    # Reporting success checks the current epoch/window AGAIN inside SQLite.
    try:
        report = journal.record_result(
            epoch=epoch,
            expected_handoff_mac=claim.handoff_mac,
            reported_success=result.exit_code == 0,
            seconds_reader=clock,
            handoff_key=handoff_key,
        )
    except (StrangeLaunchReconciliationError, ValueError) as exc:
        raise StrangeReconciledNativeLaunchError(
            "native process returned but durable outcome is unresolved"
        ) from exc
    if result.exit_code != 0:
        raise StrangeReconciledNativeLaunchError(
            "native process exited unsuccessfully; failure durably reported"
        )
    return StrangeReconciledNativeResultV1(run=result, report=report)
