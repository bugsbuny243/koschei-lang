"""Deterministic authority-free spatial layout for Koschei Universe.

Coordinates are derived from canonical node identity/digest and kind. The layout
is display metadata only: it cannot grant, revoke, or mutate authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math

from .universe_projection_v1 import UniverseProjectionV1

_CTX = b"koschei.universe-spatial/v1\x00"
_RING_BY_KIND = {
    "project": 0,
    "service": 1,
    "storage": 1,
    "guardian": 1,
    "module": 2,
    "package": 2,
    "test": 3,
    "utility": 3,
}


class UniverseSpatialLayoutError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class UniverseSpatialNodeV1:
    node_id: str
    ring: int
    angle_microrad: int
    radius_units: int
    size_units: int


@dataclass(frozen=True, slots=True)
class UniverseSpatialLayoutV1:
    projection_digest: bytes
    nodes: tuple[UniverseSpatialNodeV1, ...]
    layout_digest: bytes
    authority: bool = False


def _angle(seed: bytes) -> int:
    raw = int.from_bytes(seed[:8], "big")
    return raw % 6_283_185


def spatial_layout_v1(projection: UniverseProjectionV1) -> UniverseSpatialLayoutV1:
    if not isinstance(projection, UniverseProjectionV1) or projection.authority:
        raise UniverseSpatialLayoutError("authority-free canonical projection required")

    out: list[UniverseSpatialNodeV1] = []
    h = hashlib.sha3_256(_CTX + projection.projection_digest)
    for node in sorted(projection.nodes, key=lambda n: n.node_id):
        ring = _RING_BY_KIND[node.kind]
        seed = hashlib.sha3_256(
            _CTX + node.node_id.encode("utf-8") + b"\x00" + node.canonical_digest
        ).digest()
        angle = 0 if ring == 0 else _angle(seed)
        # Integer logical units keep backend layout deterministic and renderer-neutral.
        radius = (0, 220, 420, 620)[ring]
        jitter = 0 if ring == 0 else int.from_bytes(seed[8:10], "big") % 61 - 30
        radius += jitter
        size = 72 if node.kind == "project" else 46 if node.kind in {"service", "storage", "guardian"} else 34
        item = UniverseSpatialNodeV1(node.node_id, ring, angle, radius, size)
        out.append(item)
        h.update(
            b"N\x00" + node.node_id.encode("utf-8") + b"\x00"
            + ring.to_bytes(1, "big") + angle.to_bytes(4, "big")
            + radius.to_bytes(2, "big", signed=True) + size.to_bytes(2, "big")
        )
    return UniverseSpatialLayoutV1(projection.projection_digest, tuple(out), h.digest(), False)
