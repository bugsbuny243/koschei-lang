"""Koschei formal composite Library Risk Evidence v1.

Combines independent fail-closed boundary/behavior facts into deterministic evidence.
This is deliberately NOT an ML risk score and cannot grant/revoke authority. It
records which security dimensions changed together so Sentinel can reason over a
stable, compiler/runtime-owned fact surface.

Core law: observation != judgment != authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from .library_boundary_v1 import LibraryPrecursorFactV1
from .library_behavior_baseline_v1 import LibraryBehaviorDeltaV1

_CONTEXT = b"koschei.library-risk-evidence/v1\x00"
_ALLOWED_DIMENSIONS = frozenset({
    "identity", "authority", "target", "resource", "parser", "artifact",
})


class LibraryRiskEvidenceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RiskDimensionFactV1:
    dimension: str
    reason: str
    fact_digest: bytes


@dataclass(frozen=True, slots=True)
class CompositeLibraryRiskEvidenceV1:
    artifact_digest: bytes
    dimensions: tuple[RiskDimensionFactV1, ...]
    evidence_digest: bytes

    @property
    def compound(self) -> bool:
        return len({item.dimension for item in self.dimensions}) >= 2


def _fail(message: str) -> None:
    raise LibraryRiskEvidenceError(message)


def _d32(value: bytes, label: str) -> bytes:
    if not isinstance(value, bytes) or len(value) != 32:
        _fail(f"{label} must be exactly 32 bytes")
    return value


def _dimension_for_reason(reason: str) -> str:
    if reason in {"artifact-substitution", "behavior-artifact-identity-drift"}:
        return "artifact"
    if reason in {"authority-expansion", "behavior-new-effect"}:
        return "authority"
    if reason in {"missing-exact-target", "behavior-target-expansion"}:
        return "target"
    if reason in {"cpu-budget-exceeded", "memory-budget-exceeded",
                  "behavior-cpu-drift", "behavior-memory-drift"}:
        return "resource"
    if reason in {"input-budget-exceeded", "nesting-budget-exceeded",
                  "behavior-input-drift", "behavior-nesting-drift"}:
        return "parser"
    return "identity"


def compose_library_risk_evidence_v1(*, artifact_digest: bytes,
    precursors: Iterable[LibraryPrecursorFactV1] = (),
    deltas: Iterable[LibraryBehaviorDeltaV1] = ()) -> CompositeLibraryRiskEvidenceV1:
    artifact = _d32(artifact_digest, "artifact digest")
    facts: dict[tuple[str, str, bytes], RiskDimensionFactV1] = {}

    for precursor in precursors:
        if not isinstance(precursor, LibraryPrecursorFactV1):
            _fail("canonical precursor required")
        if precursor.artifact_digest != artifact:
            _fail("cannot compose evidence across artifact identities")
        digest = _d32(precursor.observation_digest, "precursor digest")
        dimension = _dimension_for_reason(precursor.reason)
        fact = RiskDimensionFactV1(dimension, precursor.reason, digest)
        facts[(dimension, precursor.reason, digest)] = fact

    for delta in deltas:
        if not isinstance(delta, LibraryBehaviorDeltaV1):
            _fail("canonical behavior delta required")
        digest = _d32(delta.delta_digest, "delta digest")
        reason = f"behavior-{delta.kind}"
        dimension = _dimension_for_reason(reason)
        fact = RiskDimensionFactV1(dimension, reason, digest)
        facts[(dimension, reason, digest)] = fact

    if not facts:
        _fail("risk evidence requires at least one security fact")

    ordered = tuple(sorted(facts.values(), key=lambda x: (x.dimension, x.reason, x.fact_digest)))
    if any(item.dimension not in _ALLOWED_DIMENSIONS for item in ordered):
        _fail("unknown risk dimension")
    payload = [artifact]
    for item in ordered:
        payload.extend((item.dimension.encode("ascii"), item.reason.encode("ascii"), item.fact_digest))
    evidence_digest = hashlib.sha3_256(_CONTEXT + b"evidence\x00" + b"\x00".join(payload)).digest()
    return CompositeLibraryRiskEvidenceV1(artifact, ordered, evidence_digest)
