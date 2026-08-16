"""Authenticator-style temporal access handles for Koschei Object Space v1.

The handle rotates with wall-clock slots while canonical object identity and
source bytes remain stable. This avoids rewriting a large project every 30
seconds while still making an observed access handle short-lived.

This is not TOTP and is not a human authentication code. It is a machine access
binding over project id + reality epoch + time slot. Storage epoch rotation is a
separate operation that changes physical object locators.

A process-local high-water guard rejects rollback to a slot that this trusted
process has already advanced beyond. Cross-restart rollback resistance still
requires the external Trust Plane/session broker to persist the trusted slot floor;
this module does not pretend process memory is durable authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import math
import threading
import time


_CONTEXT = b"koschei.object-space.temporal-access/v1\x00"
_TEMPORAL_KEY_BYTES = 64
_PROJECT_ID_BYTES = 16
_HANDLE_BYTES = 64

_SLOT_LOCK = threading.RLock()
_SLOT_HIGHWATER: dict[tuple[bytes, int], int] = {}


class TemporalAccessError(ValueError):
    """Raised when a temporal access handle is malformed, stale or forged."""


@dataclass(frozen=True, slots=True)
class TemporalAccessPolicy:
    period_seconds: int = 30

    def __post_init__(self) -> None:
        if (
            not isinstance(self.period_seconds, int)
            or isinstance(self.period_seconds, bool)
            or not 10 <= self.period_seconds <= 300
        ):
            raise TemporalAccessError(
                "temporal access period must be an integer in the 10..300 second range"
            )


def _project_id(value: object) -> bytes:
    if not isinstance(value, bytes) or len(value) != _PROJECT_ID_BYTES or not any(value):
        raise TemporalAccessError("project id must be exactly 16 non-zero bytes")
    return value


def _temporal_key(value: object) -> bytes:
    if not isinstance(value, bytes) or len(value) != _TEMPORAL_KEY_BYTES or not any(value):
        raise TemporalAccessError("temporal access key must be exactly 64 non-zero bytes")
    return value


def _epoch(value: object) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 1
        or value > (1 << 64) - 1
    ):
        raise TemporalAccessError("reality epoch must be a positive uint64")
    return value


def temporal_slot(
    *,
    now: float | int | None = None,
    policy: TemporalAccessPolicy = TemporalAccessPolicy(),
) -> int:
    moment = time.time() if now is None else now
    if isinstance(moment, bool) or not isinstance(moment, (int, float)):
        raise TemporalAccessError("temporal access time must be numeric")
    if not math.isfinite(float(moment)) or moment < 0:
        raise TemporalAccessError("temporal access time must be finite and non-negative")
    return int(moment) // policy.period_seconds


def _slot_key(project_id: bytes, policy: TemporalAccessPolicy) -> tuple[bytes, int]:
    return project_id, policy.period_seconds


def _require_not_rolled_back(
    project_id: bytes,
    slot: int,
    policy: TemporalAccessPolicy,
) -> None:
    with _SLOT_LOCK:
        previous = _SLOT_HIGHWATER.get(_slot_key(project_id, policy))
        if previous is not None and slot < previous:
            raise TemporalAccessError(
                "temporal access clock rolled back behind the trusted process high-water slot"
            )


def _commit_slot(
    project_id: bytes,
    slot: int,
    policy: TemporalAccessPolicy,
) -> None:
    with _SLOT_LOCK:
        key = _slot_key(project_id, policy)
        previous = _SLOT_HIGHWATER.get(key)
        if previous is not None and slot < previous:
            raise TemporalAccessError(
                "temporal access clock rolled back behind the trusted process high-water slot"
            )
        if previous is None or slot > previous:
            _SLOT_HIGHWATER[key] = slot


def _mac(
    *,
    temporal_key: bytes,
    project_id: bytes,
    epoch: int,
    slot: int,
    policy: TemporalAccessPolicy,
) -> bytes:
    payload = (
        _CONTEXT
        + project_id
        + epoch.to_bytes(8, "big")
        + slot.to_bytes(8, "big")
        + policy.period_seconds.to_bytes(2, "big")
    )
    return hmac.new(temporal_key, payload, hashlib.sha3_512).digest()


def issue_temporal_handle(
    *,
    temporal_key: bytes,
    project_id: bytes,
    epoch: int,
    now: float | int | None = None,
    policy: TemporalAccessPolicy = TemporalAccessPolicy(),
) -> bytes:
    key = _temporal_key(temporal_key)
    project = _project_id(project_id)
    reality_epoch = _epoch(epoch)
    slot = temporal_slot(now=now, policy=policy)
    _require_not_rolled_back(project, slot, policy)
    handle = _mac(
        temporal_key=key,
        project_id=project,
        epoch=reality_epoch,
        slot=slot,
        policy=policy,
    )
    _commit_slot(project, slot, policy)
    return handle


def verify_temporal_handle(
    handle: bytes,
    *,
    temporal_key: bytes,
    project_id: bytes,
    epoch: int,
    now: float | int | None = None,
    policy: TemporalAccessPolicy = TemporalAccessPolicy(),
) -> None:
    if not isinstance(handle, bytes) or len(handle) != _HANDLE_BYTES:
        raise TemporalAccessError("temporal access handle must be exactly 64 bytes")
    key = _temporal_key(temporal_key)
    project = _project_id(project_id)
    reality_epoch = _epoch(epoch)
    slot = temporal_slot(now=now, policy=policy)
    _require_not_rolled_back(project, slot, policy)
    expected = _mac(
        temporal_key=key,
        project_id=project,
        epoch=reality_epoch,
        slot=slot,
        policy=policy,
    )
    if not hmac.compare_digest(handle, expected):
        raise TemporalAccessError(
            "temporal access handle is stale, cross-project, cross-epoch or forged"
        )
    # Only a cryptographically valid handle may advance the high-water slot. A
    # forged future-slot probe therefore cannot pin the process into the future.
    _commit_slot(project, slot, policy)


def _reset_process_highwater_for_tests(project_id: bytes | None = None) -> None:
    """Test-only isolation helper; production code must never lower trusted time."""
    with _SLOT_LOCK:
        if project_id is None:
            _SLOT_HIGHWATER.clear()
            return
        project = _project_id(project_id)
        for key in tuple(_SLOT_HIGHWATER):
            if key[0] == project:
                del _SLOT_HIGHWATER[key]
