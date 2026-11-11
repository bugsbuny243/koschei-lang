from __future__ import annotations

import pytest

from koschei.mir_semantic_fallback_audit_v1 import MirSemanticFallbackAuditV1


def test_acquisition_audit_rejects_canonical_facts_on_ast_lane() -> None:
    audit = MirSemanticFallbackAuditV1(
        canonical_fact_count=2,
        execution_mode="ast_compat_v1",
        ast_compat_conflict=True,
        native_support_reasons=("unsupported MIR instruction MirVariantIs",),
    )

    with pytest.raises(ValueError, match="canonical MIR semantic facts"):
        audit.assert_acquisition_safe()


def test_audit_never_accepts_authority_promotion() -> None:
    audit = MirSemanticFallbackAuditV1(
        canonical_fact_count=0,
        execution_mode="mir_native_v1",
        ast_compat_conflict=False,
        native_support_reasons=(),
        authority=True,
    )

    with pytest.raises(ValueError, match="must never carry authority"):
        audit.assert_acquisition_safe()


def test_native_canonical_lane_is_acquisition_safe_slice() -> None:
    audit = MirSemanticFallbackAuditV1(
        canonical_fact_count=2,
        execution_mode="mir_native_v1",
        ast_compat_conflict=False,
        native_support_reasons=(),
    )

    audit.assert_acquisition_safe()
