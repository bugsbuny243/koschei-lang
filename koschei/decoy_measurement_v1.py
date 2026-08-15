"""Measurement helpers for Koschei deception-plane attack simulation v1.

This module measures observable properties; it does not claim absence of side
channels. CI results are treated as regression signals, not proofs.
"""

from __future__ import annotations

from dataclasses import dataclass
import statistics
import time
from typing import Callable

from .read_authorization_v1 import ReadGrant, read_with_grant


@dataclass(frozen=True, slots=True)
class ProbeMetrics:
    probes: int
    canonical_reader_calls: int
    unique_view_digests: int
    unique_ratio: float
    min_size: int
    max_size: int
    mean_size: float
    median_ns: float
    p95_ns: float


def _percentile(values: list[int], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * q))))
    return float(ordered[index])


def measure_unauthorized_probes(
    *,
    project_id: str,
    object_id: str,
    start_epoch: int,
    probes: int,
    stale_grant: ReadGrant,
    deception_key: bytes,
    authorization_key: bytes,
    canonical_reader: Callable[[str], bytes],
) -> ProbeMetrics:
    if probes <= 0:
        raise ValueError("probes must be positive")

    calls = 0

    def counted_reader(oid: str) -> bytes:
        nonlocal calls
        calls += 1
        return canonical_reader(oid)

    digests: set[str] = set()
    sizes: list[int] = []
    timings: list[int] = []

    for offset in range(probes):
        epoch = start_epoch + offset
        began = time.perf_counter_ns()
        view = read_with_grant(
            project_id=project_id,
            object_id=object_id,
            epoch=epoch,
            grant=stale_grant,
            canonical_reader=counted_reader,
            deception_key=deception_key,
            authorization_key=authorization_key,
        )
        timings.append(time.perf_counter_ns() - began)
        if view.provenance != "decoy" or view.deployable:
            raise AssertionError("unauthorized measurement escaped decoy path")
        digests.add(view.view_digest)
        sizes.append(len(view.content))

    return ProbeMetrics(
        probes=probes,
        canonical_reader_calls=calls,
        unique_view_digests=len(digests),
        unique_ratio=len(digests) / probes,
        min_size=min(sizes),
        max_size=max(sizes),
        mean_size=float(statistics.fmean(sizes)),
        median_ns=float(statistics.median(timings)),
        p95_ns=_percentile(timings, 0.95),
    )
