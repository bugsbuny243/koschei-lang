"""Koschei-native Intent Reality v1.

Intent separates deciding *what should happen* from owning authority to make it
happen. An Intent is an immutable, non-executing commitment derived from a
canonical native value plus an exact world-adapter target and action.

It is not a function call, syscall, HTTP request, transaction send, process spawn,
or signing operation. World adapters may later admit an Intent only when separate
authority matches its exact digest.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from . import native_value_domains_v1 as base

_CONTEXT = b"koschei.native-intent-reality/v1\x00"
MAX_LABEL_BYTES_V1 = 128


class NativeIntentRealityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class IntentRealityV1:
    adapter: str
    action: str
    value: base.NativeValue
    value_digest: bytes
    intent_digest: bytes

    def __repr__(self) -> str:
        return (
            f"IntentRealityV1(adapter={self.adapter!r}, action={self.action!r}, "
            "value=<committed>, intent=<committed>)"
        )


def _fail(message: str) -> None:
    raise NativeIntentRealityError(message)


def _label(value: str, name: str) -> bytes:
    if not isinstance(value, str) or not value:
        _fail(f"{name} must be a non-empty string")
    raw = value.encode("utf-8")
    if len(raw) > MAX_LABEL_BYTES_V1:
        _fail(f"{name} exceeds {MAX_LABEL_BYTES_V1} bytes")
    if value != value.strip() or any(ord(ch) < 0x20 for ch in value):
        _fail(f"{name} is not canonical")
    return raw


def _encode(value: base.NativeValue) -> bytes:
    if not isinstance(value, base.NativeValue):
        _fail("intent requires canonical NativeValue")
    if value.domain == base.WHOLE:
        if not isinstance(value.value, int) or isinstance(value.value, bool):
            _fail("intent carries non-canonical whole")
        return b"W" + int(value.value).to_bytes(8, "big", signed=True)
    if value.domain == base.TRUTH:
        if not isinstance(value.value, bool):
            _fail("intent carries non-canonical truth")
        return b"T" + (b"\x01" if value.value else b"\x00")
    if value.domain == base.GLYPHS:
        if not isinstance(value.value, str):
            _fail("intent carries non-canonical glyphs")
        raw = value.value.encode("utf-8")
        if len(raw) > base.MAX_GLYPHS_RESULT_BYTES:
            _fail("intent glyphs exceed native result budget")
        return b"G" + len(raw).to_bytes(4, "big") + raw
    _fail("intent carries unsupported native domain")


def derive_native_intent_reality_v1(*, adapter: str, action: str,
    value: base.NativeValue) -> IntentRealityV1:
    adapter_raw = _label(adapter, "adapter")
    action_raw = _label(action, "action")
    encoded = _encode(value)
    value_digest = hashlib.sha3_256(_CONTEXT + b"value\x00" + encoded).digest()
    payload = (
        len(adapter_raw).to_bytes(2, "big") + adapter_raw
        + len(action_raw).to_bytes(2, "big") + action_raw
        + value_digest
    )
    intent_digest = hashlib.sha3_256(_CONTEXT + b"intent\x00" + payload).digest()
    return IntentRealityV1(adapter, action, value, value_digest, intent_digest)


def verify_native_intent_reality_v1(intent: IntentRealityV1) -> bool:
    if not isinstance(intent, IntentRealityV1):
        _fail("canonical IntentRealityV1 required")
    rebuilt = derive_native_intent_reality_v1(
        adapter=intent.adapter, action=intent.action, value=intent.value
    )
    if rebuilt.value_digest != intent.value_digest or rebuilt.intent_digest != intent.intent_digest:
        _fail("intent commitment mismatch")
    return True
