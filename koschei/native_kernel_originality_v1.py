"""Originality provenance for Koschei native semantic kernel v1."""

from __future__ import annotations

from .originality_contract_v1 import (
    LEGACY_KEYWORD_DEBT_V1,
    SurfaceProvenance,
    audit_keyword_surface,
)
from .native_kernel_v1 import native_surface_words_v1


NATIVE_KERNEL_WORD_PROVENANCE_V1 = {
    "witness": SurfaceProvenance(
        invariant="deterministic-execution",
        rationale=(
            "witness denotes an immutable node in a closed dependency reality; source order "
            "has no execution meaning and the node cannot be reassigned like a variable."
        ),
        collision_reviewed=True,
    ),
    "resolve": SurfaceProvenance(
        invariant="event-horizon-isolation",
        rationale=(
            "resolve selects the one observable root of a closed object graph and forces every "
            "admitted witness to contribute to that reality; it is not early control flow."
        ),
        collision_reviewed=True,
    ),
    "sum": SurfaceProvenance(
        invariant="deterministic-execution",
        rationale=(
            "sum names the general mathematical addition relation inside an immutable value "
            "graph; it is prefix graph vocabulary rather than a borrowed infix operator."
        ),
        collision_reviewed=True,
    ),
    "difference": SurfaceProvenance(
        invariant="deterministic-execution",
        rationale=(
            "difference names the general mathematical subtraction relation inside the native "
            "value graph without inheriting an existing language's operator grammar."
        ),
        collision_reviewed=True,
    ),
    "product": SurfaceProvenance(
        invariant="deterministic-execution",
        rationale=(
            "product names the general mathematical multiplication relation inside the native "
            "value graph without inheriting an existing language's operator grammar."
        ),
        collision_reviewed=True,
    ),
}


def audit_native_kernel_surface_v1():
    current = set(LEGACY_KEYWORD_DEBT_V1) | set(native_surface_words_v1())
    return audit_keyword_surface(
        current,
        provenance=NATIVE_KERNEL_WORD_PROVENANCE_V1,
    )
