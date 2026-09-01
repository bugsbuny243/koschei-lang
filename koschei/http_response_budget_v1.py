"""Backend-independent HTTP response transport guards for Koschei Library v1.

The numeric byte limit and content-encoding policy are semantic contracts, not
interpreter tuning knobs. Native code generation must consume the same constants
when emitting its HTTP runtime.
"""
from __future__ import annotations

from typing import BinaryIO

HTTP_RESPONSE_MAX_BYTES_V1 = 1_048_576
HTTP_RESPONSE_BUDGET_ERROR_V1 = "KSNET_RESPONSE_BUDGET"
HTTP_CONTENT_ENCODING_ERROR_V1 = "KSNET_CONTENT_ENCODING"


class HttpResponseBudgetV1Error(ValueError):
    """Raised when one response exceeds the canonical v1 body budget."""

    code = HTTP_RESPONSE_BUDGET_ERROR_V1

    def __init__(self, *, limit: int = HTTP_RESPONSE_MAX_BYTES_V1) -> None:
        self.limit = limit
        super().__init__(
            f"{self.code}: HTTP response body exceeds {limit} byte budget"
        )


class HttpContentEncodingV1Error(ValueError):
    """Raised when HTTP body representation is not canonical v1 identity."""

    code = HTTP_CONTENT_ENCODING_ERROR_V1

    def __init__(self, encoding: str) -> None:
        self.encoding = encoding
        super().__init__(
            f"{self.code}: unsupported HTTP content encoding: {encoding}"
        )


def validate_http_content_encoding_v1(value: str | None) -> None:
    """Accept only the identity HTTP body representation for Library v1.

    Missing/empty Content-Encoding is HTTP identity semantics. Explicit
    `identity` is accepted case-insensitively. Any other coding fails closed so
    interpreter/native byte budgets cannot silently observe different bodies.
    """

    if value is None:
        return
    if not isinstance(value, str):
        raise TypeError("HTTP content encoding must be text or None")
    normalized = value.strip().lower()
    if normalized in {"", "identity"}:
        return
    raise HttpContentEncodingV1Error(value.strip())


def _stream_content_encoding_v1(stream: BinaryIO) -> str | None:
    """Extract Content-Encoding when `stream` is an HTTP response object.

    Plain binary streams used by tests do not carry HTTP headers and therefore
    represent already-canonical identity bytes. A response object with a headers
    surface must provide a mapping-like `get` method; malformed host integration
    fails closed instead of silently skipping the transport guard.
    """

    headers = getattr(stream, "headers", None)
    if headers is None:
        return None
    getter = getattr(headers, "get", None)
    if not callable(getter):
        raise TypeError("HTTP response headers must provide get(name)")
    value = getter("Content-Encoding")
    if value is not None and not isinstance(value, str):
        raise TypeError("HTTP Content-Encoding header must be text or None")
    return value


def read_bounded_response_body_v1(
    stream: BinaryIO,
    *,
    limit: int = HTTP_RESPONSE_MAX_BYTES_V1,
) -> bytes:
    """Read one canonical identity response without silent truncation.

    HTTP response objects are rejected before body materialization when they
    advertise a non-identity Content-Encoding. At most `limit + 1` identity
    bytes are then accumulated. Reads may legally return fewer bytes than
    requested before EOF, so the sentinel budget is consumed in a loop rather
    than trusting one host-language `read()` call to fill it.
    """

    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError("HTTP response byte budget must be a non-negative integer")

    validate_http_content_encoding_v1(_stream_content_encoding_v1(stream))

    remaining = limit + 1
    chunks: list[bytes] = []
    total = 0
    while remaining > 0:
        chunk = stream.read(remaining)
        if not isinstance(chunk, (bytes, bytearray)):
            raise TypeError("HTTP response body reader must return bytes")
        if not chunk:
            break
        piece = bytes(chunk)
        chunks.append(piece)
        total += len(piece)
        if total > limit:
            raise HttpResponseBudgetV1Error(limit=limit)
        remaining -= len(piece)
        if remaining < 0:
            raise HttpResponseBudgetV1Error(limit=limit)

    return b"".join(chunks)
