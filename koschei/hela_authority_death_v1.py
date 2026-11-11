"""Hela Authority Death v1.

Records irreversible revocation tombstones so sacrificed/revoked authority cannot
be resurrected through replay, stale epoch, alternate reality, or forked state.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib

_CTX=b"koschei.hela-authority-death/v1\x00"

class AuthorityDeathError(ValueError): pass

def _d32(v: bytes, n: str) -> bytes:
    if not isinstance(v, bytes) or len(v)!=32:
        raise AuthorityDeathError(f"{n} must be exactly 32 bytes")
    return v

@dataclass(frozen=True, slots=True)
class AuthorityTombstoneV1:
    principal_digest: bytes
    authority_id: str
    death_epoch: int
    reality_digest: bytes
    cause_digest: bytes
    previous_tombstone: bytes
    tombstone_digest: bytes


def bury_authority_v1(*, principal_digest: bytes, authority_id: str, death_epoch: int,
    reality_digest: bytes, cause_digest: bytes, previous_tombstone: bytes=b"\x00"*32) -> AuthorityTombstoneV1:
    p=_d32(principal_digest,"principal_digest"); r=_d32(reality_digest,"reality_digest")
    c=_d32(cause_digest,"cause_digest"); prev=_d32(previous_tombstone,"previous_tombstone")
    if not authority_id or death_epoch<1: raise AuthorityDeathError("invalid authority/death epoch")
    body=b"\x00".join((p,authority_id.encode(),death_epoch.to_bytes(8,"big"),r,c,prev))
    d=hashlib.sha3_256(_CTX+body).digest()
    return AuthorityTombstoneV1(p,authority_id,death_epoch,r,c,prev,d)


def authority_remains_dead_v1(tombstone: AuthorityTombstoneV1, *, principal_digest: bytes,
    authority_id: str, candidate_epoch: int) -> bool:
    try: p=_d32(principal_digest,"principal_digest")
    except AuthorityDeathError: return True
    return (p==tombstone.principal_digest and authority_id==tombstone.authority_id
        and candidate_epoch>=tombstone.death_epoch)


def resurrection_attempt_v1(tombstone: AuthorityTombstoneV1, *, principal_digest: bytes,
    authority_id: str, candidate_epoch: int) -> bool:
    return authority_remains_dead_v1(tombstone, principal_digest=principal_digest,
        authority_id=authority_id, candidate_epoch=candidate_epoch)
