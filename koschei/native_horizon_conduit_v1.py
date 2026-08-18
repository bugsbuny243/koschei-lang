"""Koschei-native Horizon Conduit v1.

A Horizon Conduit admits one committed terminal Horizon state into one exact
Signal Reality slot. It is not mutable shared state, a global variable, object
reference, callback, event bus, or implicit dependency injection.

The conduit binds:
- exact source Horizon trace digest;
- exact terminal Horizon state digest;
- exact target signal slot;
- exact projection mode.

V1 projections:
- value: admit the terminal canonical native value;
- ordinal: admit the terminal temporal ordinal as whole.

Producing a PulseFrame does not execute the target Reality and conveys no execution
or host authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Literal

from . import native_value_domains_v1 as base
from .native_horizon_reality_v1 import HorizonTraceV1
from .native_pulse_reality_v1 import PulseFrameV1

HorizonProjectionV1 = Literal["value", "ordinal"]
_ALLOWED = frozenset({"value", "ordinal"})
_CONTEXT = b"koschei.native-horizon-conduit/v1\x00"
MAX_SIGNAL_SLOT = 65535


class NativeHorizonConduitError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class HorizonConduitContractV1:
    source_trace_digest: bytes
    terminal_state_digest: bytes
    target_signal_slot: int
    projection: HorizonProjectionV1
    contract_digest: bytes


def _fail(message: str) -> None:
    raise NativeHorizonConduitError(message)


def _digest(value: bytes, label: str) -> bytes:
    if not isinstance(value, bytes) or len(value) != 32:
        _fail(f"{label} must be exactly 32 bytes")
    return value


def bind_native_horizon_conduit_v1(
    trace: HorizonTraceV1,
    *,
    target_signal_slot: int,
    projection: HorizonProjectionV1 = "value",
) -> HorizonConduitContractV1:
    if not isinstance(trace, HorizonTraceV1) or not trace.states:
        _fail("canonical non-empty HorizonTraceV1 required")
    if not isinstance(target_signal_slot, int) or isinstance(target_signal_slot, bool):
        _fail("target signal slot must be an integer")
    if not 0 <= target_signal_slot <= MAX_SIGNAL_SLOT:
        _fail("target signal slot exceeds v1 range")
    if projection not in _ALLOWED:
        _fail("unsupported Horizon projection")

    source = _digest(trace.trace_digest, "source trace digest")
    terminal = _digest(trace.states[-1].state_digest, "terminal state digest")
    payload = (
        source
        + terminal
        + target_signal_slot.to_bytes(2, "big")
        + projection.encode("ascii")
    )
    contract = hashlib.sha3_256(_CONTEXT + payload).digest()
    return HorizonConduitContractV1(source, terminal, target_signal_slot, projection, contract)


def project_native_horizon_conduit_v1(
    trace: HorizonTraceV1,
    contract: HorizonConduitContractV1,
    *,
    frame_ordinal: int = 0,
) -> PulseFrameV1:
    if not isinstance(trace, HorizonTraceV1) or not trace.states:
        _fail("canonical non-empty HorizonTraceV1 required")
    if not isinstance(contract, HorizonConduitContractV1):
        _fail("canonical Horizon conduit contract required")
    if not isinstance(frame_ordinal, int) or isinstance(frame_ordinal, bool) or frame_ordinal < 0:
        _fail("frame ordinal must be canonical non-negative integer")
    if trace.trace_digest != contract.source_trace_digest:
        _fail("Horizon trace does not match conduit contract")
    terminal = trace.states[-1]
    if terminal.state_digest != contract.terminal_state_digest:
        _fail("terminal Horizon state does not match conduit contract")

    if contract.projection == "value":
        value = terminal.value
    elif contract.projection == "ordinal":
        value = base.NativeValue(base.WHOLE, terminal.ordinal)
    else:
        _fail("unsupported Horizon projection")
    return PulseFrameV1(frame_ordinal, {contract.target_signal_slot: value})
