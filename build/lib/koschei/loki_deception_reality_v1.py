"""Loki Deception Reality v1.

Defensive deception for Koschei's multiverse. This module never hacks back,
never touches an attacker's system, and never grants authority. It creates
sealed decoy facts and tripwires that make unauthorized exploration observable
while preserving strict separation from canonical secrets and production state.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

_CTX = b"koschei.loki-deception/v1\x00"


class LokiDeceptionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DecoyRealityV1:
    decoy_id: str
    canonical_reality_digest: bytes
    decoy_payload_digest: bytes
    epoch: int
    decoy_digest: bytes


@dataclass(frozen=True, slots=True)
class DeceptionTripwireV1:
    decoy_digest: bytes
    observer_digest: bytes
    action: str
    tripwire_digest: bytes


def _d32(value: bytes, label: str) -> bytes:
    if not isinstance(value, bytes) or len(value) != 32:
        raise LokiDeceptionError(f"{label} must be exactly 32 bytes")
    return value


def create_decoy_reality_v1(*, decoy_id: str, canonical_reality_digest: bytes,
    decoy_payload_digest: bytes, epoch: int) -> DecoyRealityV1:
    if not decoy_id or not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 0:
        raise LokiDeceptionError("invalid decoy identity/epoch")
    canonical = _d32(canonical_reality_digest, "canonical_reality_digest")
    payload = _d32(decoy_payload_digest, "decoy_payload_digest")
    body = b"\x00".join((decoy_id.encode("utf-8"), canonical, payload,
        epoch.to_bytes(8, "big")))
    digest = hashlib.sha3_256(_CTX + b"decoy\x00" + body).digest()
    return DecoyRealityV1(decoy_id, canonical, payload, epoch, digest)


def trip_decoy_v1(decoy: DecoyRealityV1, *, observer_digest: bytes,
    action: str) -> DeceptionTripwireV1:
    if not isinstance(decoy, DecoyRealityV1):
        raise LokiDeceptionError("canonical DecoyRealityV1 required")
    observer = _d32(observer_digest, "observer_digest")
    if not action:
        raise LokiDeceptionError("action must be explicit")
    body = b"\x00".join((decoy.decoy_digest, observer, action.encode("utf-8")))
    digest = hashlib.sha3_256(_CTX + b"tripwire\x00" + body).digest()
    return DeceptionTripwireV1(decoy.decoy_digest, observer, action, digest)


def decoy_is_non_authoritative_v1(decoy: DecoyRealityV1) -> bool:
    """Decoys intentionally expose no execution/grant/sign/send surface."""
    return isinstance(decoy, DecoyRealityV1) and not any(
        hasattr(decoy, name) for name in ("execute", "grant", "sign", "send", "spawn")
    )
