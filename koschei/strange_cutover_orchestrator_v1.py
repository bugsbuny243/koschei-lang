"""Fail-closed local two-phase Strange epoch cutover coordinator v1.

Composes offline next-epoch compilation, durable HMAC-bound staging, atomic
Continuity epoch rotation, and single-claim native execution. This is NOT a
distributed cutover, privileged Trust Plane or hardware attestation system.
"""
from __future__ import annotations

from dataclasses import dataclass
import hmac
from pathlib import Path
from typing import Callable

from .mir import MirGraph
from .strange_durable_continuity_v1 import StrangeDurableContinuityV1
from .strange_epoch_handoff_v1 import StrangeEpochHandoffV1, StrangeHandoffV1
from .strange_pending_native_build_v1 import (
    PendingStrangeNativeBuildV1,
    prebuild_next_strange_native_v1,
)
from .strange_reconciled_native_run_v1 import run_reconciled_prebuilt_strange_native_v1
from .strange_runtime_observation_v1 import _verified_seconds
from .strange_supervised_native_v1 import StrangeSupervisedRunV1


class StrangeCutoverError(ValueError):
    """Candidate, boundary or durable cutover cannot be admitted."""


@dataclass(frozen=True, slots=True)
class StrangeStagedCutoverV1:
    """In-process binary plus durable handoff identifier; NOT a credential.

    Native binary bytes remain caller-held, never persisted in the journal.
    Restart recovery requires an independently authenticated exact artifact.
    """
    pending: PendingStrangeNativeBuildV1
    handoff: StrangeHandoffV1
    prepared_at_seconds: int
    authority: bool = False
    version: int = 1


def _store(value: StrangeDurableContinuityV1) -> StrangeDurableContinuityV1:
    if not isinstance(value, StrangeDurableContinuityV1):
        raise StrangeCutoverError("typed local Continuity store required")
    return value


def _candidate_matches_handoff(
    mir: MirGraph,
    store: StrangeDurableContinuityV1,
    staged: StrangeStagedCutoverV1,
    deployment_id: str,
    veyra_digest: str,
) -> bool:
    if not isinstance(mir, MirGraph) or not isinstance(staged, StrangeStagedCutoverV1):
        return False
    if staged.version != 1 or staged.authority is not False:
        return False
    if not isinstance(staged.pending, PendingStrangeNativeBuildV1):
        return False
    if not isinstance(staged.handoff, StrangeHandoffV1):
        return False
    staged.pending.assert_consistent()
    p, h = staged.pending.pending_projection, staged.handoff
    return (
        h.state == "STAGED" and h.authority is False and h.version == 1
        and h.continuity_id == store.continuity_id
        and h.old_epoch == p.previous_epoch and h.next_epoch == p.target_epoch
        and h.next_start_seconds == p.starts_at_seconds
        and h.source_sha256 == p.source_sha256
        and h.native_sha256 == staged.pending.native_sha256
        and h.mir_fingerprint == mir.fingerprint
        and h.deployment_id == deployment_id and h.veyra_digest == veyra_digest
        and isinstance(staged.prepared_at_seconds, int)
        and not isinstance(staged.prepared_at_seconds, bool)
        and 0 <= staged.prepared_at_seconds < h.next_start_seconds
    )


def prepare_and_stage_next_epoch_v1(
    mir: MirGraph,
    *,
    continuity_store: StrangeDurableContinuityV1,
    trust_plane_seed: bytes,
    expected_current_epoch: int,
    expected_current_start_seconds: int,
    seconds_reader: Callable[[], int],
    deployment_id: str,
    veyra_digest: str,
    go_executable: str | Path,
    expected_go_sha256: str,
    handoff_key: bytes,
    build_timeout_seconds: int = 90,
) -> StrangeStagedCutoverV1:
    """Build only epoch N+1 while N is active; atomically stage HMAC metadata.

    Compiler execution happens OUTSIDE SQLite transactions. The stage CAS
    rechecks canonical Continuity and current window after compilation.
    """
    store = _store(continuity_store)
    try:
        clock = _verified_seconds(seconds_reader)
        store.require_active_window(
            expected_epoch=expected_current_epoch,
            expected_start_seconds=expected_current_start_seconds,
            observed_seconds=clock(),
        )
        pending = prebuild_next_strange_native_v1(
            mir,
            continuity_store=store,
            trust_plane_seed=trust_plane_seed,
            expected_current_epoch=expected_current_epoch,
            expected_current_start_seconds=expected_current_start_seconds,
            seconds_reader=clock,
            deployment_id=deployment_id,
            veyra_digest=veyra_digest,
            go_executable=go_executable,
            expected_go_sha256=expected_go_sha256,
            build_timeout_seconds=build_timeout_seconds,
        )
        pending.assert_consistent()
        p = pending.pending_projection
        if (p.previous_epoch != expected_current_epoch
                or p.target_epoch != expected_current_epoch + 1
                or p.starts_at_seconds != expected_current_start_seconds + 120):
            raise StrangeCutoverError("builder returned wrong epoch or scheduled boundary")
        prepared_at = clock()
        store.require_active_window(
            expected_epoch=expected_current_epoch,
            expected_start_seconds=expected_current_start_seconds,
            observed_seconds=prepared_at,
        )
        handoff = StrangeEpochHandoffV1(store).stage(
            expected_old_epoch=expected_current_epoch,
            expected_old_start_seconds=expected_current_start_seconds,
            deployment_id=deployment_id,
            veyra_digest=veyra_digest,
            mir_fingerprint=mir.fingerprint,
            source_sha256=p.source_sha256,
            native_binary=pending.binary,
            seconds_reader=clock,
            handoff_key=handoff_key,
        )
        staged = StrangeStagedCutoverV1(pending, handoff, prepared_at)
        if not _candidate_matches_handoff(
            mir, store, staged, deployment_id, veyra_digest
        ):
            raise StrangeCutoverError("staged candidate binding mismatch")
        return staged
    except Exception as exc:
        if isinstance(exc, StrangeCutoverError):
            raise
        raise StrangeCutoverError("next epoch preparation/staging failed closed") from exc


def activate_and_reconcile_cutover_v1(
    mir: MirGraph,
    *,
    continuity_store: StrangeDurableContinuityV1,
    staged: StrangeStagedCutoverV1,
    handoff_key: bytes,
    trust_plane_seed: bytes,
    seconds_reader: Callable[[], int],
    deployment_id: str,
    veyra_digest: str,
    attestation_key: bytes,
    expected_go_sha256: str,
    run_timeout_seconds: int = 10,
    poll_interval_seconds: float = 0.05,
) -> StrangeSupervisedRunV1:
    """Rotate once at [next_start, next_start+120), then claim & run once.

    Activation is durable BEFORE native launch. If the launch/report fails,
    NEVER rewind the epoch or auto-retry the same (Continuity,epoch) pair.
    """
    store = _store(continuity_store)
    try:
        if not _candidate_matches_handoff(
            mir, store, staged, deployment_id, veyra_digest
        ):
            raise StrangeCutoverError("staged candidate is invalid or substituted")
        if staged.pending.go_executable_sha256 != expected_go_sha256:
            raise StrangeCutoverError("pinned compiler digest mismatch")
        clock = _verified_seconds(seconds_reader)
        now = clock()
        h = staged.handoff
        if now < staged.prepared_at_seconds:
            raise StrangeCutoverError("clock rollback since prepare/stage")
        if not h.next_start_seconds <= now < h.next_start_seconds + 120:
            raise StrangeCutoverError("cutover outside exact next epoch boundary")
        journal = StrangeEpochHandoffV1(store)
        stored = journal.read(h.old_epoch)
        if stored != h or not hmac.compare_digest(stored.handoff_mac, h.handoff_mac):
            raise StrangeCutoverError("durable staged HMAC record changed")
        # A second monotonic read rejects intra-transition clock rewind
        # before the durable epoch mutation.
        clock()
        activated = journal.activate(
            expected_old_epoch=h.old_epoch,
            expected_handoff_mac=h.handoff_mac,
            seconds_reader=clock,
            handoff_key=handoff_key,
        )
        if activated.state != "ACTIVATED" or not journal.retired(h.old_epoch):
            raise StrangeCutoverError("activation/old-epoch retirement not confirmed")
    except Exception as exc:
        if isinstance(exc, StrangeCutoverError):
            raise
        raise StrangeCutoverError("cutover activation rejected; no launch started") from exc

    # Never wrap this in rollback/retry logic: claim_once and result telemetry
    # are intentionally durable, and may require operator intervention.
    try:
        return run_reconciled_prebuilt_strange_native_v1(
            mir,
            continuity_store=store,
            pending=staged.pending,
            handoff_key=handoff_key,
            expected_handoff_mac=staged.handoff.handoff_mac,
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
        raise StrangeCutoverError(
            "epoch activated but native launch/outcome unresolved or failed; "
            "do not replay this epoch, investigate durable launch journal"
        ) from exc
