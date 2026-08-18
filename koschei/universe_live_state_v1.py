"""Koschei Universe Live State v1.

Binds runtime telemetry to a canonical UniverseProjection without turning the UI
or telemetry stream into an authority source. Only authenticated state can alter
visual security status.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib

from .universe_projection_v1 import UniverseProjectionV1

_CTX=b"koschei.universe-live-state/v1\x00"

class UniverseLiveStateError(ValueError): pass

def _d32(v: bytes, name: str) -> bytes:
    if not isinstance(v, bytes) or len(v) != 32:
        raise UniverseLiveStateError(f"{name} must be exactly 32 bytes")
    return v

@dataclass(frozen=True, slots=True)
class UniverseEventV1:
    node_id: str
    event_kind: str
    evidence_digest: bytes
    epoch: int

@dataclass(frozen=True, slots=True)
class UniverseLiveStateV1:
    projection_digest: bytes
    epoch: int
    events: tuple[UniverseEventV1,...]
    state_digest: bytes
    authority: bool=False

_ALLOWED=frozenset({"portal-activity","quarantine","fork","rollback","authority-death","budget-block","admission-denied","admission-accepted"})

def bind_live_state_v1(*, projection: UniverseProjectionV1,
    events: tuple[UniverseEventV1,...]) -> UniverseLiveStateV1:
    if not isinstance(projection, UniverseProjectionV1):
        raise UniverseLiveStateError("canonical projection required")
    node_ids={n.node_id for n in projection.nodes}
    h=hashlib.sha3_256(_CTX+projection.projection_digest+projection.epoch.to_bytes(8,"big"))
    for e in sorted(events,key=lambda x:(x.epoch,x.node_id,x.event_kind,x.evidence_digest)):
        if e.node_id not in node_ids or e.event_kind not in _ALLOWED:
            raise UniverseLiveStateError("event must bind known node and canonical event kind")
        if e.epoch < projection.epoch:
            raise UniverseLiveStateError("stale event cannot mutate current universe view")
        _d32(e.evidence_digest,"evidence_digest")
        h.update(e.node_id.encode()+b"\x00"+e.event_kind.encode()+b"\x00"+e.epoch.to_bytes(8,"big")+e.evidence_digest)
    return UniverseLiveStateV1(projection.projection_digest,projection.epoch,tuple(events),h.digest(),False)
