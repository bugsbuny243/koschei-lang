"""Authenticator-style temporal access handles for Koschei Object Space v1.

The handle rotates with wall-clock slots while canonical object identity and
source bytes remain stable.  This avoids rewriting a large project every 30
seconds while still making an observed access handle short-lived.

This is not TOTP and is not a human authentication code.  It is a machine access
binding over project id + reality epoch + time slot.  Storage epoch rotation is a
separate operation that changes physical object locators.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import math
import time


_CONTEXT = b"koschei.object-space.temporal-access/v1\x00"
_TEMPORAL_KEY_BYTES = 64
_PROJECT_ID_BYTES = 16
_HANDLE_BYTES = 64


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
    payload = (
        _CONTEXT
        + project
        + reality_epoch.to_bytes(8, "big")
        + slot.to_bytes(8, "big")
        + policy.period_seconds.to_bytes(2, "big")
    )
    return hmac.new(key, payload, hashlib.sha3_512).digest()


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
    expected = issue_temporal_handle(
        temporal_key=temporal_key,
        project_id=project_id,
        epoch=epoch,
        now=now,
        policy=policy,
    )
    if not hmac.compare_digest(handle, expected):
        raise TemporalAccessError(
            "temporal access handle is stale, cross-project, cross-epoch or forged"
        )
