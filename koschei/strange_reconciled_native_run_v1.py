"""Local single-attempt reconciliation around an activated Strange Linux worker.

An atomic SQLite claim is committed BEFORE invoking the verified, supervised
sealed-memfd launcher. One reported result is committed after it returns.
Failures leave a durable FAILED/CLAIMED record, NEVER an implicit retry or
rollback to an old epoch. This remains optional, non-authoritative Python:
neither fork/exec nor remote effects are atomic with SQLite.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .mir import MirGraph
from .strange_activated_candidate_launch_v1 import (
    StrangeActivatedCandidateError,
    run_activated_prebuilt_strange_native_v1,
)
from .strange_durable_continuity_v1 import StrangeDurableContinuityV1
from .strange_durable_launch_reconciliation_v1 import (
    StrangeDurableLaunchReconciliationV1,
    StrangeLaunchAttemptV1,
    StrangeLaunchReconciliationError,
)
from .strange_pending_native_build_v1 import PendingStrangeNativeBuildV1
from .strange_runtime_observation_v1 import (
    StrangeRuntimeObservationError,
    _verified_seconds,
)
from .strange_supervised_native_v1 import StrangeSupervisedRunV1


class StrangeReconciledNativeRunError(ValueError):
    """No verified, reconciled successful local launch result is available."""


@dataclass(frozen=True, slots=True)
class StrangeReconciledNativeRunV1:
    observation: StrangeSupervisedRunV1
    launch_report: StrangeLaunchAttemptV1
    authority: bool = False
    version: int = 1


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
) -> StrangeReconciledNativeRunV1:
    """Reserve once, run once, report outcome once (locally only).

    Success is a SELF-REPORTED execution observation, not trustworthy
    process measurement, an approval of side effects or a signing token.
    If the reporting transaction fails, a prior CLAIMED record remains
    unresolved. Never retry an unknown launch automatically.
    """
    if not isinstance(continuity_store, StrangeDurableContinuityV1):
        raise StrangeReconciledNativeRunError("durable Continuity required")
    if not isinstance(pending, PendingStrangeNativeBuildV1):
        raise StrangeReconciledNativeRunError("typed future native candidate required")
    clock = _verified_seconds(seconds_reader)
    epoch = pending.pending_projection.target_epoch
    try:
        journal = StrangeDurableLaunchReconciliationV1(continuity_store)
        attempt = journal.claim_once(
            expected_epoch=epoch,
            expected_handoff_mac=expected_handoff_mac,
            expected_native_sha256=pending.native_sha256,
            handoff_key=handoff_key,
            seconds_reader=clock,
        )
    except (StrangeLaunchReconciliationError, StrangeRuntimeObservationError) as exc:
        raise StrangeReconciledNativeRunError(
            "prelaunch attempt already consumed or not admissible"
        ) from exc

    # Do not accept a post-execution result until the durable report commits.
    def report(succeeded: bool) -> StrangeLaunchAttemptV1:
        try:
            return journal.record_result(
                epoch=attempt.epoch,
                expected_handoff_mac=attempt.handoff_mac,
                reported_success=succeeded,
                seconds_reader=clock,
                handoff_key=handoff_key,
            )
        except (StrangeLaunchReconciliationError, StrangeRuntimeObservationError) as exc:
            raise StrangeReconciledNativeRunError(
                "launch outcome could not be durably reconciled; operator action required"
            ) from exc

    try:
        observed = run_activated_prebuilt_strange_native_v1(
            mir,
            continuity_store=continuity_store,
            pending=pending,
            handoff_key=handoff_key,
            expected_handoff_mac=attempt.handoff_mac,
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
        # A failed attempt is terminal for this epoch.  If even this report
        # cannot be stored, CLAIMED remains visible (no automatic retry).
        report(False)
        raise StrangeReconciledNativeRunError(
            "activated native worker failed; no epoch rollback permitted"
        ) from exc

    if not isinstance(observed, StrangeSupervisedRunV1):
        report(False)
        raise StrangeReconciledNativeRunError("invalid native runner observation")
    if observed.exit_code != 0 or observed.authority is not False:
        report(False)
        raise StrangeReconciledNativeRunError("native worker did not finish successfully")
    if observed.observed_epoch != attempt.epoch or observed.native_sha256 != attempt.native_sha256:
        report(False)
        raise StrangeReconciledNativeRunError("worker observation conflicts with durable claim")

    complete = report(True)
    if complete.state != "REPORTED_OK" or complete.authority is not False:
        raise StrangeReconciledNativeRunError("runner outcome is not an authority-free OK report")
    return StrangeReconciledNativeRunV1(
        observation=observed, launch_report=complete,
    )
