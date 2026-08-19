"""Koschei Universe forces v1.

A presentation/interpretation layer that maps authenticated canonical live-state
evidence onto Koschei's six native Universe forces. It cannot mint authority,
change admission, or mutate runtime state.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib

from .universe_projection_v1 import UniverseProjectionV1
from .universe_live_state_v1 import UniverseLiveStateV1

_CTX=b"koschei.universe-forces/v1\x00"

class UniverseForcesError(ValueError): pass

@dataclass(frozen=True, slots=True)
class UniverseForceV1:
    name: str
    mode: str
    node_ids: tuple[str,...]
    evidence_digest: bytes

@dataclass(frozen=True, slots=True)
class UniverseForcesV1:
    projection_digest: bytes
    state_digest: bytes
    forces: tuple[UniverseForceV1,...]
    forces_digest: bytes
    authority: bool=False

# Native Koschei mythology, intentionally not aliases of third-party characters.
_FORCE_RULES=(
    ("Aegis", frozenset({"quarantine","fork","rollback","authority-death"}), "contain"),
    ("Oracle", frozenset({"budget-block","admission-denied","authority-death"}), "analyze"),
    ("Warden", frozenset({"admission-denied","admission-accepted","authority-death"}), "govern"),
    ("Velocity", frozenset({"portal-activity","admission-accepted"}), "flow"),
    ("Abyss", frozenset({"quarantine","rollback","fork"}), "preserve"),
    ("Forge", frozenset({"admission-accepted","rollback"}), "isolate"),
)

def derive_universe_forces_v1(*, projection: UniverseProjectionV1, live: UniverseLiveStateV1) -> UniverseForcesV1:
    if not isinstance(projection, UniverseProjectionV1) or not isinstance(live, UniverseLiveStateV1):
        raise UniverseForcesError("canonical projection and live state required")
    if projection.authority or live.authority:
        raise UniverseForcesError("Universe forces must remain authority-free")
    if live.projection_digest != projection.projection_digest:
        raise UniverseForcesError("live state does not bind projection")
    known={n.node_id for n in projection.nodes}
    by_kind: dict[str,list[tuple[str,bytes]]]={}
    for e in live.events:
        if e.node_id not in known: raise UniverseForcesError("event references unknown node")
        by_kind.setdefault(e.event_kind,[]).append((e.node_id,e.evidence_digest))
    forces=[]
    root=hashlib.sha3_256(_CTX+projection.projection_digest+live.state_digest)
    for name,kinds,mode in _FORCE_RULES:
        bound=[]
        for kind in sorted(kinds):
            for node_id,digest in sorted(by_kind.get(kind,[]),key=lambda v:(v[0],v[1])):
                bound.append((kind,node_id,digest))
        if not bound: continue
        h=hashlib.sha3_256(_CTX+name.encode()+b"\x00"+mode.encode()+b"\x00")
        nodes=[]
        for kind,node_id,digest in bound:
            h.update(kind.encode()+b"\x00"+node_id.encode()+b"\x00"+digest)
            nodes.append(node_id)
        f=UniverseForceV1(name,mode,tuple(sorted(set(nodes))),h.digest())
        forces.append(f); root.update(name.encode()+b"\x00"+f.evidence_digest)
    return UniverseForcesV1(projection.projection_digest,live.state_digest,tuple(forces),root.digest(),False)
