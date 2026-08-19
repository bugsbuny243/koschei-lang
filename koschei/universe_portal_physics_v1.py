"""Deterministic authority-free portal physics for Koschei Universe.

Portal metadata is derived only from canonical relation/evidence facts. It is
renderer guidance, never an execution capability or network control primitive.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .universe_projection_v1 import UniverseEdgeV1, UniverseProjectionV1

_CTX = b"koschei.universe-portal/v1\x00"

_STYLE_BY_RELATION = {
    "depends": "gravity-link",
    "imports": "dashed-gate",
    "conduit": "energy-conduit",
    "observes": "sensor-beam",
    "persists": "anchor-bridge",
    "tests": "simulation-rift",
    "guards": "shield-arc",
}


class UniversePortalPhysicsError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class UniversePortalV1:
    source_id: str
    destination_id: str
    relation: str
    style: str
    phase_milli: int
    pulse_milli: int
    width_milli: int
    evidence_digest: bytes


@dataclass(frozen=True, slots=True)
class UniversePortalPhysicsV1:
    projection_digest: bytes
    portals: tuple[UniversePortalV1, ...]
    portal_digest: bytes
    authority: bool = False


def _portal_for(edge: UniverseEdgeV1) -> UniversePortalV1:
    style = _STYLE_BY_RELATION.get(edge.relation)
    if style is None:
        raise UniversePortalPhysicsError("unsupported canonical relation")
    seed = hashlib.sha3_256(
        _CTX
        + edge.source_id.encode("utf-8") + b"\x00"
        + edge.destination_id.encode("utf-8") + b"\x00"
        + edge.relation.encode("utf-8") + b"\x00"
        + edge.evidence_digest
    ).digest()
    phase = int.from_bytes(seed[:2], "big") % 1000
    pulse = 650 + int.from_bytes(seed[2:4], "big") % 1351
    base_width = {
        "gravity-link": 900,
        "dashed-gate": 850,
        "energy-conduit": 1800,
        "sensor-beam": 700,
        "anchor-bridge": 1500,
        "simulation-rift": 1100,
        "shield-arc": 1600,
    }[style]
    return UniversePortalV1(
        edge.source_id,
        edge.destination_id,
        edge.relation,
        style,
        phase,
        pulse,
        base_width,
        edge.evidence_digest,
    )


def portal_physics_v1(projection: UniverseProjectionV1) -> UniversePortalPhysicsV1:
    if not isinstance(projection, UniverseProjectionV1) or projection.authority:
        raise UniversePortalPhysicsError("authority-free canonical projection required")
    portals = tuple(
        _portal_for(edge)
        for edge in sorted(
            projection.edges,
            key=lambda e: (e.source_id, e.destination_id, e.relation, e.evidence_digest),
        )
    )
    h = hashlib.sha3_256(_CTX + projection.projection_digest)
    for p in portals:
        h.update(
            b"P\x00" + p.source_id.encode("utf-8") + b"\x00"
            + p.destination_id.encode("utf-8") + b"\x00"
            + p.relation.encode("utf-8") + b"\x00"
            + p.style.encode("utf-8") + b"\x00"
            + p.phase_milli.to_bytes(2, "big")
            + p.pulse_milli.to_bytes(2, "big")
            + p.width_milli.to_bytes(2, "big")
            + p.evidence_digest
        )
    return UniversePortalPhysicsV1(projection.projection_digest, portals, h.digest(), False)
