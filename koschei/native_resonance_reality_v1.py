"""Koschei-native Resonance Reality v1.

Resonance is a canonical temporal edge derived from Pulse Reality outputs. It is
not an event loop, callback, observer object, subscription API, or hidden control
flow. A resonance exists only when two adjacent resolved realities differ in a
way admitted by the selected resonance mode.

Modes:
- change: emit on any canonical value change;
- rise: emit only truth no -> yes;
- fall: emit only truth yes -> no.

The resulting records are immutable facts. They do not execute downstream code or
carry authority. A later conduit may admit these facts into another Reality.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Literal

from . import native_value_domains_v1 as base
from .native_pulse_reality_v1 import PulseTraceV1

ResonanceMode = Literal["change", "rise", "fall"]
_ALLOWED = frozenset({"change", "rise", "fall"})
_CONTEXT = b"koschei.native-resonance-reality/v1\x00"


class NativeResonanceRealityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResonanceFactV1:
    ordinal: int
    mode: ResonanceMode
    before_digest: bytes
    after_digest: bytes
    fact_digest: bytes

    def __repr__(self) -> str:
        return (
            f"ResonanceFactV1(ordinal={self.ordinal}, mode={self.mode!r}, "
            "before=<committed>, after=<committed>, fact=<committed>)"
        )


@dataclass(frozen=True, slots=True)
class ResonanceTraceV1:
    facts: tuple[ResonanceFactV1, ...]
    trace_digest: bytes


def _fail(message: str) -> None:
    raise NativeResonanceRealityError(message)


def _value_bytes(value: base.NativeValue) -> bytes:
    if not isinstance(value, base.NativeValue):
        _fail("resonance requires canonical native values")
    if value.domain == base.WHOLE:
        if not isinstance(value.value, int) or isinstance(value.value, bool):
            _fail("non-canonical whole in resonance trace")
        return b"W" + int(value.value).to_bytes(8, "big", signed=True)
    if value.domain == base.TRUTH:
        if not isinstance(value.value, bool):
            _fail("non-canonical truth in resonance trace")
        return b"T" + (b"\x01" if value.value else b"\x00")
    if value.domain == base.GLYPHS:
        if not isinstance(value.value, str):
            _fail("non-canonical glyphs in resonance trace")
        raw = value.value.encode("utf-8")
        return b"G" + len(raw).to_bytes(4, "big") + raw
    _fail("unsupported native domain in resonance trace")


def _digest_value(value: base.NativeValue) -> bytes:
    return hashlib.sha3_256(_CONTEXT + b"value\x00" + _value_bytes(value)).digest()


def _matches(mode: ResonanceMode, before: base.NativeValue, after: base.NativeValue) -> bool:
    if before.domain != after.domain:
        _fail("resonance cannot cross native value domains")
    if mode == "change":
        return _value_bytes(before) != _value_bytes(after)
    if before.domain != base.TRUTH:
        _fail(f"{mode} resonance requires truth-valued Pulse Reality")
    b = bool(before.value)
    a = bool(after.value)
    return (not b and a) if mode == "rise" else (b and not a)


def derive_native_resonance_reality_v1(trace: PulseTraceV1, *, mode: ResonanceMode) -> ResonanceTraceV1:
    if not isinstance(trace, PulseTraceV1):
        _fail("canonical PulseTraceV1 required")
    if mode not in _ALLOWED:
        _fail("unsupported resonance mode")
    if len(trace.outputs) < 2:
        _fail("resonance requires at least two pulse outputs")

    facts: list[ResonanceFactV1] = []
    chain = hashlib.sha3_256(_CONTEXT + b"trace\x00" + trace.trace_digest)
    for ordinal, (before, after) in enumerate(zip(trace.outputs, trace.outputs[1:]), start=1):
        if not _matches(mode, before, after):
            continue
        before_digest = _digest_value(before)
        after_digest = _digest_value(after)
        payload = (
            ordinal.to_bytes(4, "big")
            + mode.encode("ascii")
            + before_digest
            + after_digest
        )
        fact_digest = hashlib.sha3_256(_CONTEXT + b"fact\x00" + payload).digest()
        facts.append(ResonanceFactV1(ordinal, mode, before_digest, after_digest, fact_digest))
        chain.update(fact_digest)

    return ResonanceTraceV1(tuple(facts), chain.digest())
