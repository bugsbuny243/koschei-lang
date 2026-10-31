"""Launch a previously prepared native candidate ONLY after staged epoch activation.

The pending binary is not directly an authority. This opt-in Linux bootstrap
checks the activated HMAC-bound handoff against the exact candidate native
bytes, reproduces the canonical active-epoch MIR-Go source digest, issues a
current-epoch attestation and launches through the existing supervised sealed
memfd runner. It does NOT automatically transfer work or terminate a
separately launched old process; it offers no privileged-effect authority.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Callable

from .mir import MirGraph
from .strange_verified_native_build_v1 import _hex256, StrangeVerifiedNativeBuildError
from .strange_durable_continuity_v1 import (
    StrangeDurableContinuityError,
    StrangeDurableContinuityV1,
)
from .strange_epoch_handoff_v1 import (
    StrangeEpochHandoffError,
    StrangeEpochHandoffV1,
    _mac as handoff_mac,
    _secret as handoff_secret,
)
from .strange_native_admission_v1 import (
    StrangeNativeAdmissionError,
    issue_strange_native_attestation_v1,
)
from .strange_pending_native_build_v1 import (
    PendingStrangeNativeBuildV1,
    StrangePendingNativeBuildError,
)
from .strange_representation_epoch_v1 import (
    StrangeRepresentationEpochError,
    project_strange_epoch_go_v1,
)
from .strange_runtime_observation_v1 import (
    StrangeRuntimeObservationError,
    _verified_seconds,
)
from .strange_supervised_native_v1 import (
    StrangeSupervisedNativeError,
    StrangeSupervisedRunV1,
    run_strange_supervised_native_v1,
)


class StrangeActivatedCandidateError(ValueError):
    """Prepared native artifact is not eligible for current epoch launch."""


def run_activated_prebuilt_strange_native_v1(
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
    """Recheck activated identity and run exact pending bytes as local worker.

    Never pass a signing key, a Library secret or an effect capability to the
    child. Caller-controlled Python keys/clock are not independent trust roots.
    """
    if not isinstance(mir, MirGraph):
        raise StrangeActivatedCandidateError("sealed canonical MIR required")
    try:
        mir.assert_sealed()
    except ValueError as exc:
        raise StrangeActivatedCandidateError("canonical MIR not sealed") from exc
    if not isinstance(continuity_store, StrangeDurableContinuityV1):
        raise StrangeActivatedCandidateError("durable Continuity store required")
    if not isinstance(pending, PendingStrangeNativeBuildV1):
        raise StrangeActivatedCandidateError("pending native candidate required")
    try:
        pending.assert_consistent()
        key = handoff_secret(handoff_key)
        clock = _verified_seconds(seconds_reader)
    except (
        StrangePendingNativeBuildError, StrangeEpochHandoffError,
        StrangeRuntimeObservationError,
    ) as exc:
        raise StrangeActivatedCandidateError("invalid pending candidate or trust inputs") from exc
    proposal = pending.pending_projection
    try:
        _hex256(expected_go_sha256)
        _hex256(expected_handoff_mac)
    except StrangeVerifiedNativeBuildError as exc:
        raise StrangeActivatedCandidateError("canonical pinned digest required") from exc
    if (
        proposal.target_epoch != proposal.previous_epoch + 1
        or not hmac.compare_digest(pending.go_executable_sha256, expected_go_sha256)
    ):
        raise StrangeActivatedCandidateError("pending compiler/epoch binding mismatch")

    try:
        journal = StrangeEpochHandoffV1(continuity_store)
        stage = journal.read(proposal.previous_epoch)
        if stage.state != "ACTIVATED" or not journal.retired(stage.old_epoch):
            raise StrangeActivatedCandidateError("native candidate handoff is not activated")
        expected = handoff_mac(key, stage)
        if (
            not isinstance(expected_handoff_mac, str)
            or not hmac.compare_digest(expected, stage.handoff_mac)
            or not hmac.compare_digest(expected, expected_handoff_mac)
        ):
            raise StrangeActivatedCandidateError("untrusted or substituted handoff proof")
        if (
            stage.continuity_id != continuity_store.continuity_id
            or stage.old_epoch != proposal.previous_epoch
            or stage.next_epoch != proposal.target_epoch
            or stage.next_start_seconds != proposal.starts_at_seconds
            or stage.source_sha256 != proposal.source_sha256
            or stage.native_sha256 != pending.native_sha256
            or stage.deployment_id != deployment_id
            or stage.veyra_digest != veyra_digest
            or stage.mir_fingerprint != mir.fingerprint
        ):
            raise StrangeActivatedCandidateError("activated candidate identity mismatch")
        continuity_store.require_active_window(
            expected_epoch=stage.next_epoch,
            expected_start_seconds=stage.next_start_seconds,
            observed_seconds=clock(),
        )
        # A pending projection is never promoted by a type cast. The active
        # canonical projector must recompute the same source independently.
        source, active = project_strange_epoch_go_v1(
            mir,
            trust_plane_seed=trust_plane_seed,
            continuity=continuity_store.as_continuity_authority(),
            expected_epoch=stage.next_epoch,
            starts_at_seconds=stage.next_start_seconds,
            seconds_reader=clock,
            deployment_id=deployment_id,
            veyra_digest=veyra_digest,
        )
        if (
            active.source_sha256 != stage.source_sha256
            or hashlib.sha256(source.encode("utf-8")).hexdigest() != stage.source_sha256
            or hashlib.sha256(pending.binary).hexdigest() != stage.native_sha256
        ):
            raise StrangeActivatedCandidateError("active source/native bytes mismatch")
        # Admission key policy is external; this low-level issuer does not
        # independently prove the compiler's source-to-binary provenance.
        attestation = issue_strange_native_attestation_v1(
            receipt=active,
            native_binary=pending.binary,
            deployment_id=deployment_id,
            veyra_digest=veyra_digest,
            mir_fingerprint=mir.fingerprint,
            continuity=continuity_store.as_continuity_authority(),
            expected_epoch=stage.next_epoch,
            starts_at_seconds=stage.next_start_seconds,
            seconds_reader=clock,
            attestation_key=attestation_key,
        )
        # The sealed runner checks the exact binary and Continuity again
        # immediately before exec and then polls it while the worker runs.
        return run_strange_supervised_native_v1(
            continuity_store=continuity_store,
            attestation=attestation,
            native_binary=pending.binary,
            expected_source_sha256=active.source_sha256,
            deployment_id=deployment_id,
            veyra_digest=veyra_digest,
            mir_fingerprint=mir.fingerprint,
            expected_epoch=stage.next_epoch,
            expected_start_seconds=stage.next_start_seconds,
            seconds_reader=clock,
            attestation_key=attestation_key,
            run_timeout_seconds=run_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
    except (
        StrangeDurableContinuityError,
        StrangeEpochHandoffError,
        StrangePendingNativeBuildError,
        StrangeNativeAdmissionError,
        StrangeRepresentationEpochError,
        StrangeRuntimeObservationError,
        StrangeSupervisedNativeError,
    ) as exc:
        raise StrangeActivatedCandidateError("activated native launch rejected") from exc
