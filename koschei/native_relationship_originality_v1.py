"""Originality provenance for Koschei native relationship vocabulary."""

from __future__ import annotations

from .native_kernel_v1 import native_surface_words_v1
from .native_relationship_v1 import RELATION_WORD_V1
from .originality_contract_v1 import (
    LEGACY_KEYWORD_DEBT_V1,
    SurfaceProvenance,
    audit_keyword_surface,
)


NATIVE_RELATIONSHIP_WORD_PROVENANCE_V1 = {
    "witness": SurfaceProvenance(
        invariant="deterministic-execution",
        rationale="witness is an immutable node in the closed native value reality, not a sequential binding.",
        collision_reviewed=True,
    ),
    "resolve": SurfaceProvenance(
        invariant="event-horizon-isolation",
        rationale="resolve selects the one observable root of a closed native value reality, not control flow.",
        collision_reviewed=True,
    ),
    "sum": SurfaceProvenance(
        invariant="deterministic-execution",
        rationale="sum is prefix mathematical graph vocabulary and has no source-order execution semantics.",
        collision_reviewed=True,
    ),
    "difference": SurfaceProvenance(
        invariant="deterministic-execution",
        rationale="difference is prefix mathematical graph vocabulary rather than inherited operator grammar.",
        collision_reviewed=True,
    ),
    "product": SurfaceProvenance(
        invariant="deterministic-execution",
        rationale="product is prefix mathematical graph vocabulary rather than inherited operator grammar.",
        collision_reviewed=True,
    ),
    RELATION_WORD_V1: SurfaceProvenance(
        invariant="authority-explicit",
        rationale=(
            "conduit denotes a sealed value relationship slot whose target identity, digest, frontend, "
            "epoch, authority, effect and resource ceilings live in authenticated Object Space reality; "
            "it is not a module namespace or filesystem import spelling."
        ),
        collision_reviewed=True,
    ),
}


def audit_native_relationship_surface_v1():
    current = set(LEGACY_KEYWORD_DEBT_V1) | set(native_surface_words_v1()) | {RELATION_WORD_V1}
    return audit_keyword_surface(current, provenance=NATIVE_RELATIONSHIP_WORD_PROVENANCE_V1)
