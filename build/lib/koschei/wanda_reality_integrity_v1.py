"""Wanda Reality Integrity v1.

Tamper-evident reality commitments for Koschei's multiverse architecture.
A state may evolve, but an already admitted past cannot be silently rewritten.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib

_CTX = b"koschei.wanda-reality/v1\x00"
ZERO = b"\x00" * 32

class RealityIntegrityError(ValueError): pass

def _d32(v: bytes, n: str) -> bytes:
    if not isinstance(v, bytes) or len(v) != 32:
        raise RealityIntegrityError(f"{n} must be exactly 32 bytes")
    return v

@dataclass(frozen=True, slots=True)
class RealityCommitmentV1:
    reality_id: str
    epoch: int
    state_digest: bytes
    authority_digest: bytes
    previous_commitment: bytes
    commitment_digest: bytes

def commit_reality_v1(*, reality_id: str, epoch: int, state_digest: bytes,
    authority_digest: bytes, previous_commitment: bytes = ZERO) -> RealityCommitmentV1:
    if not reality_id or epoch < 0: raise RealityIntegrityError("invalid reality identity/epoch")
    state = _d32(state_digest, "state_digest")
    auth = _d32(authority_digest, "authority_digest")
    prev = _d32(previous_commitment, "previous_commitment")
    body = b"\x00".join((reality_id.encode(), str(epoch).encode(), state, auth, prev))
    digest = hashlib.sha3_256(_CTX + body).digest()
    return RealityCommitmentV1(reality_id, epoch, state, auth, prev, digest)

def extends_reality_v1(parent: RealityCommitmentV1, child: RealityCommitmentV1) -> bool:
    return (parent.reality_id == child.reality_id
        and child.epoch == parent.epoch + 1
        and child.previous_commitment == parent.commitment_digest)

def detect_reality_fork_v1(a: RealityCommitmentV1, b: RealityCommitmentV1) -> bool:
    """Two different commitments claiming the same reality+epoch are a fork."""
    return (a.reality_id == b.reality_id and a.epoch == b.epoch
        and a.commitment_digest != b.commitment_digest)

def detects_rollback_v1(current: RealityCommitmentV1, candidate: RealityCommitmentV1) -> bool:
    return current.reality_id == candidate.reality_id and candidate.epoch <= current.epoch
