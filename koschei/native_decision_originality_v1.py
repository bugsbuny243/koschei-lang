"""Originality provenance for Koschei native decision reality v1."""

from __future__ import annotations

from .native_decision_realities_v1 import native_decision_surface_words_v1
from .native_value_domain_originality_v1 import NATIVE_VALUE_DOMAIN_WORD_PROVENANCE_V1
from .originality_contract_v1 import LEGACY_KEYWORD_DEBT_V1, SurfaceProvenance, audit_keyword_surface


NATIVE_DECISION_WORD_PROVENANCE_V1 = dict(NATIVE_VALUE_DOMAIN_WORD_PROVENANCE_V1)
NATIVE_DECISION_WORD_PROVENANCE_V1["settle"] = SurfaceProvenance(
    invariant="deterministic-execution",
    rationale=(
        "settle binds one truth-selected candidate reality into the observable graph; "
        "it is not statement branching, fallthrough, pattern matching, or an if/else rename."
    ),
    collision_reviewed=True,
)


def audit_native_decision_surface_v1():
    current = set(LEGACY_KEYWORD_DEBT_V1) | set(native_decision_surface_words_v1())
    return audit_keyword_surface(current, provenance=NATIVE_DECISION_WORD_PROVENANCE_V1)
