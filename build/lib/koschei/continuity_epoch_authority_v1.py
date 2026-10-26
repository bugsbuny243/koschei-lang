"""Shared runtime epoch authority boundary for Koschei Continuity v1.

This module deliberately does one small job: sanctioned observer, reconstruction and
materialization gates receive the same typed Continuity interface instead of each
accepting an arbitrary epoch callback.

The bootstrap seal identifies the Continuity source role; it does not authenticate the
Python callable, prove monotonic time, survive rollback, or establish hardware trust.
Production must bind the reader behind this interface to authoritative durable/native
Continuity state.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Callable

_CTX = b"koschei.continuity-epoch-authority/v1\x00"


class ContinuityEpochAuthorityV1Error(ValueError):
    pass


EpochReader = Callable[[], int]


def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContinuityEpochAuthorityV1Error(f"{field} cannot be empty")
    return value.strip()


def _authority_digest(continuity_id: str) -> str:
    value = _text(continuity_id, "continuity_id")
    return hashlib.sha256(
        _CTX + b"identity\x00" + value.encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class ContinuityEpochAuthorityV1:
    """Typed fail-closed interface to one authoritative runtime epoch source.

    `authority=False` means this object does not grant effect authority. It is trusted
    input for liveness decisions only. The identity digest prevents accidental relabeling
    of the Continuity source role, but does not prove the reader itself is honest.
    """

    continuity_id: str
    authority_digest: str
    epoch_reader: EpochReader
    authority: bool = False
    version: int = 1

    def assert_sealed(self) -> None:
        if self.version != 1:
            raise ContinuityEpochAuthorityV1Error(
                "Continuity epoch authority requires version 1"
            )
        if self.authority is not False:
            raise ContinuityEpochAuthorityV1Error(
                "Continuity epoch authority cannot carry effect authority"
            )
        if not callable(self.epoch_reader):
            raise ContinuityEpochAuthorityV1Error(
                "Continuity epoch reader must be callable"
            )
        expected = _authority_digest(self.continuity_id)
        if self.authority_digest != expected:
            raise ContinuityEpochAuthorityV1Error(
                "Continuity epoch authority identity seal mismatch"
            )

    def current_epoch(self) -> int:
        self.assert_sealed()
        try:
            value = self.epoch_reader()
        except Exception as exc:
            raise ContinuityEpochAuthorityV1Error(
                "Continuity epoch read failed closed"
            ) from exc
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ContinuityEpochAuthorityV1Error(
                "Continuity epoch source returned an invalid epoch"
            )
        return value


def bind_continuity_epoch_authority_v1(
    *,
    continuity_id: str,
    epoch_reader: EpochReader,
) -> ContinuityEpochAuthorityV1:
    """Bind one runtime epoch reader to a stable typed Continuity identity."""

    value = _text(continuity_id, "continuity_id")
    if not callable(epoch_reader):
        raise ContinuityEpochAuthorityV1Error(
            "Continuity epoch reader must be callable"
        )
    result = ContinuityEpochAuthorityV1(
        continuity_id=value,
        authority_digest=_authority_digest(value),
        epoch_reader=epoch_reader,
    )
    result.assert_sealed()
    return result
