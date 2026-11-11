"""Koschei-native Resonance Conduit v1.

A resonance conduit transfers immutable temporal facts from one Reality into the
signal surface of another Reality without callbacks, subscriptions, hidden event
loops or ambient authority. The conduit is an explicit host-provided contract that
binds one resonance mode to one destination signal slot and one admitted projection.

V1 projections:
- ordinal: admit the resonance edge ordinal as a whole value;
- occurred: admit truth yes for each admitted fact.

The conduit never executes the destination itself. It only produces canonical
PulseFrameV1 values that may later be resolved by Pulse Reality. This keeps fact
transport separate from execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Literal

from . import native_value_domains_v1 as base
from .native_pulse_reality_v1 import PulseFrameV1
from .native_resonance_reality_v1 import ResonanceFactV1, ResonanceTraceV1

Projection = Literal["ordinal", "occurred"]
_ALLOWED = frozenset({"ordinal", "occurred"})
_CONTEXT = b"koschei.native-resonance-conduit/v1\x00"
MAX_RESONANCE_CONDUIT_FRAMES_V1 = 1024


class NativeResonanceConduitError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResonanceConduitContractV1:
    destination_slot: int
    projection: Projection
    source_trace_digest: bytes
    contract_digest: bytes

    def __repr__(self) -> str:
        return (
            "ResonanceConduitContractV1(destination_slot="
            f"{self.destination_slot}, projection={self.projection!r}, "
            "source=<committed>, contract=<committed>)"
        )


@dataclass(frozen=True, slots=True)
class ResonanceConduitFramesV1:
    frames: tuple[PulseFrameV1, ...]
    transfer_digest: bytes


def _fail(message: str) -> None:
    raise NativeResonanceConduitError(message)


def bind_resonance_conduit_v1(
    trace: ResonanceTraceV1,
    *,
    destination_slot: int,
    projection: Projection,
) -> ResonanceConduitContractV1:
    if not isinstance(trace, ResonanceTraceV1):
        _fail("canonical ResonanceTraceV1 required")
    if not isinstance(destination_slot, int) or isinstance(destination_slot, bool):
        _fail("destination signal slot must be an integer")
    if not 0 <= destination_slot <= 65535:
        _fail("destination signal slot exceeds native signal range")
    if projection not in _ALLOWED:
        _fail("unsupported resonance conduit projection")
    if not isinstance(trace.trace_digest, bytes) or len(trace.trace_digest) != 32:
        _fail("resonance trace digest must be exactly 32 bytes")
    payload = (
        destination_slot.to_bytes(2, "big")
        + projection.encode("ascii")
        + trace.trace_digest
    )
    digest = hashlib.sha3_256(_CONTEXT + b"contract\x00" + payload).digest()
    return ResonanceConduitContractV1(
        destination_slot,
        projection,
        trace.trace_digest,
        digest,
    )


def _project_fact(contract: ResonanceConduitContractV1, fact: ResonanceFactV1) -> base.NativeValue:
    if contract.projection == "ordinal":
        return base.NativeValue(base.WHOLE, fact.ordinal)
    if contract.projection == "occurred":
        return base.NativeValue(base.TRUTH, True)
    _fail("non-canonical resonance conduit contract")


def materialize_resonance_conduit_v1(
    trace: ResonanceTraceV1,
    contract: ResonanceConduitContractV1,
) -> ResonanceConduitFramesV1:
    if not isinstance(trace, ResonanceTraceV1):
        _fail("canonical ResonanceTraceV1 required")
    if not isinstance(contract, ResonanceConduitContractV1):
        _fail("canonical ResonanceConduitContractV1 required")
    if trace.trace_digest != contract.source_trace_digest:
        _fail("resonance conduit source trace mismatch")
    if len(trace.facts) > MAX_RESONANCE_CONDUIT_FRAMES_V1:
        _fail("resonance conduit exceeds bounded transfer budget")

    frames: list[PulseFrameV1] = []
    chain = hashlib.sha3_256(_CONTEXT + b"transfer\x00" + contract.contract_digest)
    for ordinal, fact in enumerate(trace.facts):
        if not isinstance(fact, ResonanceFactV1):
            _fail("resonance trace contains non-canonical fact")
        value = _project_fact(contract, fact)
        frames.append(PulseFrameV1(ordinal, {contract.destination_slot: value}))
        chain.update(fact.fact_digest)
        chain.update(ordinal.to_bytes(4, "big"))

    return ResonanceConduitFramesV1(tuple(frames), chain.digest())
