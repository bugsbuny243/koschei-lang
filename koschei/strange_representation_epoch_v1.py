"""Bound a Strange native representation to one trusted deployment/epoch window.

A caller-supplied time is NOT a trust root. The readings must be supplied by a
separately isolated, monotonic Trust Plane in production. This module is an
authority-free bootstrap contract: it does not rotate running code or grant
signing, Library, Galaxy, or other critical execution authority.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import hmac

from .continuity_epoch_authority_v1 import ContinuityEpochAuthorityV1
from .mir import MirGraph
from .mir_go_native import generate_go_mir_native

_WINDOW_SECONDS = 120
_CTX = b"koschei/strange-epoch-representation/v1\x00"


class StrangeRepresentationEpochError(ValueError):
    """An epoch-bound projection cannot be admitted."""


@dataclass(frozen=True, slots=True)
class StrangeEpochProjectionV1:
    """Builder-side receipt, NOT an execution credential or observer ticket."""

    epoch: int
    starts_at_seconds: int
    expires_before_seconds: int
    source_sha256: str
    version: int = 1
    authority: bool = False


def _seconds(reader: Callable[[], int]) -> int:
    if not callable(reader):
        raise StrangeRepresentationEpochError("trusted seconds reader is required")
    try:
        now = reader()
    except Exception as exc:
        raise StrangeRepresentationEpochError("trusted seconds reader failed closed") from exc
    if not isinstance(now, int) or isinstance(now, bool) or now < 0:
        raise StrangeRepresentationEpochError("invalid trusted seconds reading")
    return now


def _text(value: str, label: str) -> bytes:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 1024:
        raise StrangeRepresentationEpochError(f"invalid {label}")
    return value.encode("utf-8")


def _fingerprint(value: str, label: str) -> bytes:
    if not isinstance(value, str) or len(value) != 64:
        raise StrangeRepresentationEpochError(f"invalid {label}")
    try:
        decoded = bytes.fromhex(value)
    except ValueError as exc:
        raise StrangeRepresentationEpochError(f"invalid {label}") from exc
    return decoded


def _frame(value: bytes) -> bytes:
    return len(value).to_bytes(8, "big") + value


def require_strange_epoch_window_v1(
    *,
    continuity: ContinuityEpochAuthorityV1,
    expected_epoch: int,
    starts_at_seconds: int,
    seconds_reader: Callable[[], int],
) -> int:
    """Require a current Continuity epoch and half-open [start,start+120) window."""
    if not isinstance(continuity, ContinuityEpochAuthorityV1):
        raise StrangeRepresentationEpochError("typed Continuity source required")
    if not isinstance(expected_epoch, int) or isinstance(expected_epoch, bool) or expected_epoch < 1:
        raise StrangeRepresentationEpochError("invalid expected epoch")
    if not isinstance(starts_at_seconds, int) or isinstance(starts_at_seconds, bool) or starts_at_seconds < 0:
        raise StrangeRepresentationEpochError("invalid window start")
    try:
        active_epoch = continuity.current_epoch()
    except ValueError as exc:
        raise StrangeRepresentationEpochError("Continuity failed closed") from exc
    if active_epoch != expected_epoch:
        raise StrangeRepresentationEpochError("stale or future Continuity epoch")
    now = _seconds(seconds_reader)
    if now < starts_at_seconds or now >= starts_at_seconds + _WINDOW_SECONDS:
        raise StrangeRepresentationEpochError("Strange representation window expired or not yet active")
    return now


def derive_strange_epoch_seed_v1(
    *,
    trust_plane_seed: bytes,
    continuity: ContinuityEpochAuthorityV1,
    expected_epoch: int,
    starts_at_seconds: int,
    seconds_reader: Callable[[], int],
    deployment_id: str,
    veyra_digest: str,
    mir_fingerprint: str,
) -> bytes:
    """Derive a non-authoritative seed for one scoped native representation.

    The Trust Plane seed must never be loaded from client configuration, source,
    CLI arguments or environment variables by the production builder.
    """
    if not isinstance(trust_plane_seed, bytes) or len(trust_plane_seed) < 32:
        raise StrangeRepresentationEpochError("Trust Plane seed must contain at least 256 bits")
    require_strange_epoch_window_v1(
        continuity=continuity,
        expected_epoch=expected_epoch,
        starts_at_seconds=starts_at_seconds,
        seconds_reader=seconds_reader,
    )
    fields = (
        _text(deployment_id, "deployment identity"),
        _fingerprint(veyra_digest, "Veyra digest"),
        _fingerprint(mir_fingerprint, "MIR fingerprint"),
        expected_epoch.to_bytes(8, "big"),
        starts_at_seconds.to_bytes(8, "big"),
        _WINDOW_SECONDS.to_bytes(4, "big"),
    )
    material = _CTX + b"".join(_frame(item) for item in fields)
    return hmac.new(trust_plane_seed, material, hashlib.sha256).digest()


def project_strange_epoch_go_v1(
    mir: MirGraph,
    *,
    trust_plane_seed: bytes,
    continuity: ContinuityEpochAuthorityV1,
    expected_epoch: int,
    starts_at_seconds: int,
    seconds_reader: Callable[[], int],
    deployment_id: str,
    veyra_digest: str,
) -> tuple[str, StrangeEpochProjectionV1]:
    """Return an opt-in Go projection and builder-only source digest receipt.

    The pre-/post-projection window checks prevent publishing a result from a
    build that crossed the epoch boundary. Deployment cutover and runtime
    admission remain separate, unimplemented obligations.
    """
    if not isinstance(mir, MirGraph):
        raise StrangeRepresentationEpochError("sealed canonical MIR required")
    mir.assert_sealed()
    seed = derive_strange_epoch_seed_v1(
        trust_plane_seed=trust_plane_seed,
        continuity=continuity,
        expected_epoch=expected_epoch,
        starts_at_seconds=starts_at_seconds,
        seconds_reader=seconds_reader,
        deployment_id=deployment_id,
        veyra_digest=veyra_digest,
        mir_fingerprint=mir.fingerprint,
    )
    source = generate_go_mir_native(mir, representation_seed=seed)
    require_strange_epoch_window_v1(
        continuity=continuity,
        expected_epoch=expected_epoch,
        starts_at_seconds=starts_at_seconds,
        seconds_reader=seconds_reader,
    )
    receipt = StrangeEpochProjectionV1(
        epoch=expected_epoch,
        starts_at_seconds=starts_at_seconds,
        expires_before_seconds=starts_at_seconds + _WINDOW_SECONDS,
        source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
    )
    return source, receipt
