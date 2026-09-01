"""Backend-independent HTTP response body budget for Koschei Library v1.

The numeric limit is a semantic contract, not an interpreter tuning knob. Native
code generation must import this same constant when emitting its bounded reader.
"""
from __future__ import annotations

from typing import BinaryIO

HTTP_RESPONSE_MAX_BYTES_V1 = 1_048_576
HTTP_RESPONSE_BUDGET_ERROR_V1 = "KSNET_RESPONSE_BUDGET"


class HttpResponseBudgetV1Error(ValueError):
    """Raised when one response exceeds the canonical v1 body budget."""

    code = HTTP_RESPONSE_BUDGET_ERROR_V1

    def __init__(self, *, limit: int = HTTP_RESPONSE_MAX_BYTES_V1) -> None:
        self.limit = limit
        super().__init__(
            f"{self.code}: HTTP response body exceeds {limit} byte budget"
        )


def read_bounded_response_body_v1(
    stream: BinaryIO,
    *,
    limit: int = HTTP_RESPONSE_MAX_BYTES_V1,
) -> bytes:
    """Read one response body without ever accepting silent truncation.

    `limit + 1` is read only as an over-limit sentinel. Exactly-at-limit bodies
    are accepted; any additional byte fails closed.
    """

    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError("HTTP response byte budget must be a non-negative integer")
    payload = stream.read(limit + 1)
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("HTTP response body reader must return bytes")
    if len(payload) > limit:
        raise HttpResponseBudgetV1Error(limit=limit)
    return bytes(payload)
