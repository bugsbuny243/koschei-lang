"""Transport shaping for protected Koschei source views.

This layer is deliberately outside compiler/source semantics. It reduces simple
response-size and timing fingerprints without claiming constant-time behavior.
The source broker remains the authority for canonical-vs-decoy provenance.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import time
from typing import Callable

from .decoy_view_broker_v1 import DecoyViewError, SourceView, read_source_view


class ReadTransportError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ShapedSourceResponse:
    object_id: str
    epoch: int
    provenance: str
    deployable: bool
    payload_length: int
    transport: bytes
    transport_digest: str
    elapsed_ns: int
    target_floor_ns: int
    floor_met: bool


Clock = Callable[[], int]
Sleeper = Callable[[float], None]


def _require_bucket(bucket_bytes: int) -> int:
    if not isinstance(bucket_bytes, int) or isinstance(bucket_bytes, bool):
        raise ReadTransportError("bucket_bytes must be an integer")
    if bucket_bytes < 512 or bucket_bytes > 16 * 1024 * 1024:
        raise ReadTransportError("bucket_bytes must be between 512 and 16777216")
    return bucket_bytes


def _require_floor(target_floor_ns: int) -> int:
    if not isinstance(target_floor_ns, int) or isinstance(target_floor_ns, bool) or target_floor_ns < 0:
        raise ReadTransportError("target_floor_ns must be a non-negative integer")
    if target_floor_ns > 5_000_000_000:
        raise ReadTransportError("target_floor_ns exceeds 5 second safety limit")
    return target_floor_ns


def _padding(*, key: bytes, object_id: str, epoch: int, length: int) -> bytes:
    if not isinstance(key, bytes) or len(key) < 32:
        raise ReadTransportError("shaping_key must contain at least 256 bits")
    if length <= 0:
        return b""
    seed = hmac.new(
        key,
        b"koschei/read-transport-shaping/v1\x00" + object_id.encode("ascii") + b"\x00" + str(epoch).encode("ascii"),
        hashlib.sha256,
    ).digest()
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(hmac.new(key, seed + counter.to_bytes(8, "big"), hashlib.sha256).digest())
        counter += 1
    return bytes(out[:length])


def shape_source_view(
    view: SourceView,
    *,
    bucket_bytes: int,
    shaping_key: bytes,
    target_floor_ns: int = 0,
    started_ns: int | None = None,
    clock_ns: Clock = time.perf_counter_ns,
    sleeper: Sleeper = time.sleep,
) -> ShapedSourceResponse:
    """Shape one already-admitted view into a fixed-size transport response.

    The payload length/provenance fields are internal metadata and are not part of
    the transport bytes. The caller deciding what metadata crosses a trust
    boundary remains responsible for not exposing those internal fields.
    """
    if not isinstance(view, SourceView):
        raise ReadTransportError("view must be SourceView")
    bucket = _require_bucket(bucket_bytes)
    floor = _require_floor(target_floor_ns)
    if not callable(clock_ns) or not callable(sleeper):
        raise ReadTransportError("clock_ns and sleeper must be callable")
    if len(view.content) > bucket:
        raise ReadTransportError("source view exceeds configured fixed transport bucket")

    start = clock_ns() if started_ns is None else started_ns
    if not isinstance(start, int):
        raise ReadTransportError("clock must return integer nanoseconds")

    pad_len = bucket - len(view.content)
    transport = view.content + _padding(
        key=shaping_key,
        object_id=view.object_id,
        epoch=view.epoch,
        length=pad_len,
    )

    before_wait = clock_ns()
    if not isinstance(before_wait, int):
        raise ReadTransportError("clock must return integer nanoseconds")
    elapsed = max(before_wait - start, 0)
    remaining = max(floor - elapsed, 0)
    if remaining:
        sleeper(remaining / 1_000_000_000)
    end = clock_ns()
    if not isinstance(end, int):
        raise ReadTransportError("clock must return integer nanoseconds")
    total_elapsed = max(end - start, 0)

    return ShapedSourceResponse(
        object_id=view.object_id,
        epoch=view.epoch,
        provenance=view.provenance,
        deployable=view.deployable,
        payload_length=len(view.content),
        transport=transport,
        transport_digest="sha256:" + hashlib.sha256(transport).hexdigest(),
        elapsed_ns=total_elapsed,
        target_floor_ns=floor,
        floor_met=total_elapsed >= floor,
    )


def read_shaped_source(
    *,
    project_id: str,
    object_id: str,
    epoch: int,
    authorized: bool,
    canonical_reader,
    deception_key: bytes,
    shaping_key: bytes,
    bucket_bytes: int,
    target_floor_ns: int = 0,
    clock_ns: Clock = time.perf_counter_ns,
    sleeper: Sleeper = time.sleep,
) -> ShapedSourceResponse:
    """Read through the canonical/decoy broker, then shape only the transport."""
    started = clock_ns()
    try:
        view = read_source_view(
            project_id=project_id,
            object_id=object_id,
            epoch=epoch,
            authorized=authorized,
            canonical_reader=canonical_reader,
            deception_key=deception_key,
        )
    except DecoyViewError:
        raise
    return shape_source_view(
        view,
        bucket_bytes=bucket_bytes,
        shaping_key=shaping_key,
        target_floor_ns=target_floor_ns,
        started_ns=started,
        clock_ns=clock_ns,
        sleeper=sleeper,
    )
