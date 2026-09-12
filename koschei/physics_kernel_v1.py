"""Canonical Koschei Physics Kernel v1 registry.

This module names the twelve cross-Universe invariants without creating a new
execution or authority path. Enforcement remains owned by the existing Khar,
Galaxy, MIR, Continuity, evidence and authorization mechanisms.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

_CTX = b"koschei.physics-kernel/v1\x00"


class PhysicsKernelError(ValueError):
    pass


CANONICAL_PHYSICS_LAWS_V1 = (
    "physics.existence.provenance-required",
    "physics.authority.conservation",
    "physics.evidence.claim-is-not-proof",
    "physics.knowledge.not-authority",
    "physics.observable.not-canonical",
    "physics.semantic.conservation",
    "physics.ambiguity.fail-closed",
    "physics.survival.no-privilege-manufacture",
    "physics.finality.no-silent-reversal",
    "physics.semantic.one-canonical-truth",
    "physics.execution.proof-carrying",
    "physics.component.no-sovereign-bypass",
)


def _physics_digest(laws: tuple[str, ...]) -> str:
    if not laws or any(not isinstance(law, str) or not law for law in laws):
        raise PhysicsKernelError("physics laws must be non-empty public identifiers")
    if len(set(laws)) != len(laws):
        raise PhysicsKernelError("duplicate physics law identifier")
    return hashlib.sha256(_CTX + b"laws\x00" + "\n".join(laws).encode("utf-8")).hexdigest()


CANONICAL_PHYSICS_DIGEST_V1 = _physics_digest(CANONICAL_PHYSICS_LAWS_V1)


@dataclass(frozen=True, slots=True)
class PhysicsKernelV1:
    laws: tuple[str, ...]
    digest: str
    version: int = 1
    authority: bool = False

    def assert_canonical(self) -> None:
        if self.version != 1:
            raise PhysicsKernelError("unsupported Physics Kernel version")
        if self.authority:
            raise PhysicsKernelError("Physics registry is not an authority credential")
        if self.laws != CANONICAL_PHYSICS_LAWS_V1:
            raise PhysicsKernelError("Physics v1 law substitution is forbidden")
        expected = _physics_digest(self.laws)
        if expected != CANONICAL_PHYSICS_DIGEST_V1 or self.digest != expected:
            raise PhysicsKernelError("Physics v1 registry seal mismatch")


def canonical_physics_v1() -> PhysicsKernelV1:
    result = PhysicsKernelV1(CANONICAL_PHYSICS_LAWS_V1, CANONICAL_PHYSICS_DIGEST_V1)
    result.assert_canonical()
    return result
