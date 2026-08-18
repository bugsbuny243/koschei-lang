"""Koschei Universe Projection v1.

Transforms authenticated project/runtime facts into an authority-free spatial
projection. The projection is display state, never an execution capability.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib

_CTX = b"koschei.universe-projection/v1\x00"

class UniverseProjectionError(ValueError): pass

def _d32(v: bytes, name: str) -> bytes:
    if not isinstance(v, bytes) or len(v) != 32:
        raise UniverseProjectionError(f"{name} must be exactly 32 bytes")
    return v

@dataclass(frozen=True, slots=True)
class UniverseNodeV1:
    node_id: str
    kind: str
    canonical_digest: bytes
    quarantined: bool = False

@dataclass(frozen=True, slots=True)
class UniverseEdgeV1:
    source_id: str
    destination_id: str
    relation: str
    evidence_digest: bytes

@dataclass(frozen=True, slots=True)
class UniverseProjectionV1:
    project_digest: bytes
    epoch: int
    nodes: tuple[UniverseNodeV1, ...]
    edges: tuple[UniverseEdgeV1, ...]
    projection_digest: bytes
    authority: bool = False

_ALLOWED_KINDS = frozenset({"project", "package", "service", "storage", "test", "guardian", "utility"})
_ALLOWED_RELATIONS = frozenset({"depends", "conduit", "observes", "persists", "tests", "guards"})

def project_universe_v1(*, project_digest: bytes, epoch: int,
    nodes: tuple[UniverseNodeV1, ...], edges: tuple[UniverseEdgeV1, ...]) -> UniverseProjectionV1:
    project = _d32(project_digest, "project_digest")
    if epoch < 0: raise UniverseProjectionError("epoch must be non-negative")
    ids=set()
    h=hashlib.sha3_256(_CTX + project + epoch.to_bytes(8,"big"))
    for n in sorted(nodes, key=lambda x:x.node_id):
        if not n.node_id or n.node_id in ids or n.kind not in _ALLOWED_KINDS:
            raise UniverseProjectionError("invalid/duplicate universe node")
        _d32(n.canonical_digest,"canonical_digest"); ids.add(n.node_id)
        h.update(b"N\x00"+n.node_id.encode()+b"\x00"+n.kind.encode()+n.canonical_digest+bytes([n.quarantined]))
    for e in sorted(edges, key=lambda x:(x.source_id,x.destination_id,x.relation)):
        if e.source_id not in ids or e.destination_id not in ids or e.relation not in _ALLOWED_RELATIONS:
            raise UniverseProjectionError("edge must bind known nodes and relation")
        _d32(e.evidence_digest,"evidence_digest")
        h.update(b"E\x00"+e.source_id.encode()+b"\x00"+e.destination_id.encode()+b"\x00"+e.relation.encode()+e.evidence_digest)
    return UniverseProjectionV1(project,epoch,tuple(nodes),tuple(edges),h.digest(),False)
