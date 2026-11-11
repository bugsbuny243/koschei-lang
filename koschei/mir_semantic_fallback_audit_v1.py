"""Evidence-only audit for canonical MIR facts that still route to AST compatibility.

The audit carries no execution authority and does not choose a runtime lane. It
makes Law 6/10 debt machine-readable: once a semantic fact has been normalized
into compiler-owned MIR, acquisition validation must be able to see whether the
public runtime would still execute source AST for that graph.
"""
from __future__ import annotations

from dataclasses import dataclass

from .mir import MirGraph
from .mir_extension_instructions_v4 import MirVariantIs, MirVariantPayload
from .mir_native_runtime import inspect_native_mir_support
from .runtime_budget import runtime_execution_mode


@dataclass(frozen=True, slots=True)
class MirSemanticFallbackAuditV1:
    canonical_fact_count: int
    execution_mode: str
    ast_compat_conflict: bool
    native_support_reasons: tuple[str, ...]
    authority: bool = False

    def assert_acquisition_safe(self) -> None:
        if self.authority:
            raise ValueError("semantic fallback audit must never carry authority")
        if self.ast_compat_conflict:
            raise ValueError(
                "canonical MIR semantic facts would execute through AST compatibility"
            )


def audit_semantic_fallback_v1(mir: MirGraph) -> MirSemanticFallbackAuditV1:
    if not isinstance(mir, MirGraph):
        raise TypeError("semantic fallback audit requires MirGraph")
    mir.assert_sealed()

    canonical_fact_count = 0
    for module in mir.in_dependency_order():
        for function in module.functions:
            for block in function.blocks:
                for instruction in block.instructions:
                    if isinstance(instruction, (MirVariantIs, MirVariantPayload)):
                        canonical_fact_count += 1

    native = inspect_native_mir_support(mir)
    mode = runtime_execution_mode(mir)
    conflict = canonical_fact_count > 0 and mode == "ast_compat_v1"
    return MirSemanticFallbackAuditV1(
        canonical_fact_count=canonical_fact_count,
        execution_mode=mode,
        ast_compat_conflict=conflict,
        native_support_reasons=native.reasons,
    )


__all__ = ["MirSemanticFallbackAuditV1", "audit_semantic_fallback_v1"]
