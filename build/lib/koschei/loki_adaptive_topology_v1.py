"""Loki Adaptive Topology v1.

Defensive deception physics for untrusted observers. The topology varies by
cryptographic evidence, never exposes canonical targets/secrets, and never
creates authority. It is deterministic for audit/replay.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib

_CTX = b"koschei.loki-adaptive-topology/v1\x00"
_FORBIDDEN = ("secret", "sign", "execute", "spawn", "root", "vormir")

class AdaptiveTopologyError(ValueError): pass

def _d32(v: bytes, name: str) -> bytes:
    if not isinstance(v, bytes) or len(v) != 32:
        raise AdaptiveTopologyError(f"{name} must be exactly 32 bytes")
    return v

@dataclass(frozen=True, slots=True)
class DecoyRouteV1:
    observer_digest: bytes
    evidence_digest: bytes
    generation: int
    route_label: str
    route_digest: bytes
    authority: bool = False


def derive_decoy_route_v1(*, observer_digest: bytes, evidence_digest: bytes,
    generation: int, surface: str) -> DecoyRouteV1:
    observer = _d32(observer_digest, "observer_digest")
    evidence = _d32(evidence_digest, "evidence_digest")
    if generation < 0 or not surface:
        raise AdaptiveTopologyError("invalid generation/surface")
    lowered = surface.lower()
    if any(word in lowered for word in _FORBIDDEN):
        raise AdaptiveTopologyError("decoy surface may not imitate privileged canonical targets")
    seed = hashlib.sha3_256(_CTX + observer + evidence + generation.to_bytes(8, "big") + surface.encode()).digest()
    label = f"mirror-{int.from_bytes(seed[:4], 'big') % 100000:05d}:{surface}"
    route = hashlib.sha3_256(_CTX + b"route\x00" + seed + label.encode()).digest()
    return DecoyRouteV1(observer, evidence, generation, label, route, False)


def route_is_non_authoritative_v1(route: DecoyRouteV1) -> bool:
    return isinstance(route, DecoyRouteV1) and route.authority is False


def topology_rotates_v1(previous: DecoyRouteV1, *, new_evidence_digest: bytes) -> bool:
    """Evidence changes force a different decoy generation/route."""
    try:
        evidence = _d32(new_evidence_digest, "new_evidence_digest")
    except AdaptiveTopologyError:
        return False
    return evidence != previous.evidence_digest
