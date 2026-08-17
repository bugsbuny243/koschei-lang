"""Koschei-native Pulse Reality v1.

Pulse is bounded temporal change inside a Reality. It is not a while/for loop,
thread, async task, sleep, callback, or scheduler primitive. A pulse consumes an
ordered host-authenticated sequence of canonical signal frames and re-resolves the
same closed witness graph once per frame.

Surface remains Signal Reality source. Temporal behavior is supplied by a Pulse
contract, so source cannot secretly widen time, iteration count, or ambient input.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Mapping, Sequence

from . import native_value_domains_v1 as base
from .native_signal_reality_v1 import (
    NativeSignalRealityError,
    evaluate_native_signal_reality_v1,
    parse_native_signal_reality_v1,
)

MAX_PULSE_FRAMES_V1 = 1024
_PULSE_CONTEXT = b"koschei.native-pulse-reality/v1\x00"


class NativePulseRealityError(NativeSignalRealityError):
    pass


@dataclass(frozen=True, slots=True)
class PulseFrameV1:
    ordinal: int
    bindings: Mapping[int, base.NativeValue]


@dataclass(frozen=True, slots=True)
class PulseTraceV1:
    outputs: tuple[base.NativeValue, ...]
    trace_digest: bytes


def _fail(code: str, message: str) -> None:
    raise NativePulseRealityError(code, message, 1, 1)


def _value_bytes(value: base.NativeValue) -> bytes:
    if value.domain == base.WHOLE:
        return b"W" + int(value.value).to_bytes(8, "big", signed=True)
    if value.domain == base.TRUTH:
        return b"T" + (b"\x01" if value.value else b"\x00")
    if value.domain == base.GLYPHS:
        raw = str(value.value).encode("utf-8")
        return b"G" + len(raw).to_bytes(4, "big") + raw
    _fail("KPUL1400", "pulse output has unsupported native domain")


def evaluate_native_pulse_reality_v1(
    source: str,
    frames: Sequence[PulseFrameV1],
) -> PulseTraceV1:
    """Resolve one immutable reality across a bounded authenticated time sequence."""
    parse_native_signal_reality_v1(source)
    if not isinstance(frames, Sequence) or isinstance(frames, (str, bytes, bytearray)):
        _fail("KPUL1200", "pulse frames must be a canonical sequence")
    if not frames:
        _fail("KPUL1201", "pulse reality requires at least one frame")
    if len(frames) > MAX_PULSE_FRAMES_V1:
        _fail("KPUL1202", f"pulse reality exceeds {MAX_PULSE_FRAMES_V1} frames")

    outputs: list[base.NativeValue] = []
    h = hashlib.sha3_256(_PULSE_CONTEXT)
    for expected, frame in enumerate(frames):
        if not isinstance(frame, PulseFrameV1):
            _fail("KPUL1203", "pulse frame must be canonical PulseFrameV1")
        if frame.ordinal != expected:
            _fail("KPUL1204", "pulse frame ordinals must be exact, contiguous and zero-based")
        try:
            output = evaluate_native_signal_reality_v1(source, frame.bindings)
        except NativeSignalRealityError as error:
            raise NativePulseRealityError(error.code, error.message, error.line, error.column) from error
        outputs.append(output)
        encoded = _value_bytes(output)
        h.update(expected.to_bytes(4, "big"))
        h.update(len(encoded).to_bytes(4, "big"))
        h.update(encoded)

    return PulseTraceV1(tuple(outputs), h.digest())
