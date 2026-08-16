"""Originality provenance for Koschei native value-domain vocabulary."""

from __future__ import annotations

from .native_value_domains_v1 import native_value_surface_words_v1
from .originality_contract_v1 import LEGACY_KEYWORD_DEBT_V1, SurfaceProvenance, audit_keyword_surface


NATIVE_VALUE_DOMAIN_WORD_PROVENANCE_V1 = {
    "witness": SurfaceProvenance(
        invariant="deterministic-execution",
        rationale="witness is an immutable graph equation rather than a sequential source binding.",
        collision_reviewed=True,
    ),
    "resolve": SurfaceProvenance(
        invariant="event-horizon-isolation",
        rationale="resolve selects the one observable graph root rather than expressing control-flow return.",
        collision_reviewed=True,
    ),
    "sum": SurfaceProvenance(
        invariant="deterministic-execution",
        rationale="sum is prefix graph mathematics with dependency-order semantics rather than infix execution syntax.",
        collision_reviewed=True,
    ),
    "difference": SurfaceProvenance(
        invariant="deterministic-execution",
        rationale="difference is prefix graph mathematics with dependency-order semantics rather than infix execution syntax.",
        collision_reviewed=True,
    ),
    "product": SurfaceProvenance(
        invariant="deterministic-execution",
        rationale="product is prefix graph mathematics with dependency-order semantics rather than infix execution syntax.",
        collision_reviewed=True,
    ),
    "truth": SurfaceProvenance(
        invariant="deterministic-execution",
        rationale="truth introduces a canonical graph value domain and is not a declaration, branch, or host-language bool syntax.",
        collision_reviewed=True,
    ),
    "yes": SurfaceProvenance(
        invariant="deterministic-execution",
        rationale="yes is the canonical affirmative truth-domain payload and has no independent control-flow meaning.",
        collision_reviewed=True,
    ),
    "no": SurfaceProvenance(
        invariant="deterministic-execution",
        rationale="no is the canonical negative truth-domain payload and has no independent control-flow meaning.",
        collision_reviewed=True,
    ),
    "glyphs": SurfaceProvenance(
        invariant="temporal-source-identity",
        rationale="glyphs denotes exact NFC UTF-8 text bytes admitted with an explicit byte budget rather than host string literal syntax.",
        collision_reviewed=True,
    ),
    "same": SurfaceProvenance(
        invariant="verifiable-effects",
        rationale="same compares only identical value domains and produces truth without implicit coercion or host equality fallback.",
        collision_reviewed=True,
    ),
    "merge": SurfaceProvenance(
        invariant="resource-linearity",
        rationale="merge combines only bounded glyph values and enforces the resulting UTF-8 byte budget before backend lowering.",
        collision_reviewed=True,
    ),
}


def audit_native_value_domain_surface_v1():
    current = set(LEGACY_KEYWORD_DEBT_V1) | set(native_value_surface_words_v1())
    return audit_keyword_surface(current, provenance=NATIVE_VALUE_DOMAIN_WORD_PROVENANCE_V1)
