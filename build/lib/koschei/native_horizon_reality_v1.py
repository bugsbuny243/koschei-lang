"""Koschei-native Horizon Reality v1.

Horizon gives a Reality bounded memory across Pulse frames without introducing
mutable globals, assignment, objects, reducers, loops, or hidden callbacks.
A horizon is an immutable chain of canonical native values. Each admitted frame
creates a new committed horizon state derived from the previous state.

Modes:
- remember: retain the latest admitted value;
- tally: accumulate whole-valued observations with checked integer semantics;
- affirm: once truth becomes yes, the horizon remains yes.

This is temporal state as evidence, not ambient mutable storage.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Literal

from . import native_value_domains_v1 as base
from .native_pulse_reality_v1 import PulseTraceV1

HorizonMode = Literal["remember", "tally", "affirm"]
_ALLOWED = frozenset({"remember", "tally", "affirm"})
_CONTEXT = b"koschei.native-horizon-reality/v1\x00"
_I64_MIN = -(1 << 63)
_I64_MAX = (1 << 63) - 1


class NativeHorizonRealityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class HorizonStateV1:
    ordinal: int
    mode: HorizonMode
    value: base.NativeValue
    previous_digest: bytes
    state_digest: bytes


@dataclass(frozen=True, slots=True)
class HorizonTraceV1:
    states: tuple[HorizonStateV1, ...]
    trace_digest: bytes


def _fail(message: str) -> None:
    raise NativeHorizonRealityError(message)


def _encode(value: base.NativeValue) -> bytes:
    if not isinstance(value, base.NativeValue):
        _fail("horizon requires canonical native values")
    if value.domain == base.WHOLE:
        if not isinstance(value.value, int) or isinstance(value.value, bool):
            _fail("non-canonical whole in horizon")
        if not _I64_MIN <= value.value <= _I64_MAX:
            _fail("whole exceeds horizon integer domain")
        return b"W" + value.value.to_bytes(8, "big", signed=True)
    if value.domain == base.TRUTH:
        if not isinstance(value.value, bool):
            _fail("non-canonical truth in horizon")
        return b"T" + (b"\x01" if value.value else b"\x00")
    if value.domain == base.GLYPHS:
        if not isinstance(value.value, str):
            _fail("non-canonical glyphs in horizon")
        raw = value.value.encode("utf-8")
        return b"G" + len(raw).to_bytes(4, "big") + raw
    _fail("unsupported native domain in horizon")


def _next(mode: HorizonMode, previous: base.NativeValue | None, current: base.NativeValue) -> base.NativeValue:
    if mode == "remember":
        return current
    if mode == "tally":
        if current.domain != base.WHOLE:
            _fail("tally horizon requires whole-valued Pulse Reality")
        total = current.value if previous is None else previous.value + current.value
        if not _I64_MIN <= total <= _I64_MAX:
            _fail("tally horizon overflow")
        return base.NativeValue(base.WHOLE, total)
    if mode == "affirm":
        if current.domain != base.TRUTH:
            _fail("affirm horizon requires truth-valued Pulse Reality")
        value = current.value if previous is None else bool(previous.value or current.value)
        return base.NativeValue(base.TRUTH, value)
    _fail("unsupported horizon mode")


def derive_native_horizon_reality_v1(trace: PulseTraceV1, *, mode: HorizonMode) -> HorizonTraceV1:
    if not isinstance(trace, PulseTraceV1):
        _fail("canonical PulseTraceV1 required")
    if mode not in _ALLOWED:
        _fail("unsupported horizon mode")
    if not trace.outputs:
        _fail("horizon requires at least one Pulse output")

    states: list[HorizonStateV1] = []
    previous_value: base.NativeValue | None = None
    previous_digest = hashlib.sha3_256(_CONTEXT + b"genesis\x00" + trace.trace_digest).digest()
    chain = hashlib.sha3_256(_CONTEXT + b"trace\x00" + trace.trace_digest)
    for ordinal, current in enumerate(trace.outputs):
        value = _next(mode, previous_value, current)
        encoded = _encode(value)
        payload = ordinal.to_bytes(4, "big") + mode.encode("ascii") + previous_digest + encoded
        state_digest = hashlib.sha3_256(_CONTEXT + b"state\x00" + payload).digest()
        state = HorizonStateV1(ordinal, mode, value, previous_digest, state_digest)
        states.append(state)
        chain.update(state_digest)
        previous_value = value
        previous_digest = state_digest

    return HorizonTraceV1(tuple(states), chain.digest())
