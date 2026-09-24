"""Canonical executable MIR v4 lowering entry-point.

This module is the explicit bridge from the normalized v4 lowerer to
compiler-owned MatchExpression lowering and checked variant construction. It
creates no backend semantic authority: match owner/payload/order/exhaustiveness
come from Typed-HIR, and constructor owner comes from the already-checked
Typed-HIR result type rather than runtime/backend name lookup.
"""
from __future__ import annotations

from .ast_nodes import CallExpression, Expression, Identifier, MatchExpression
from .mir_match_lowering_v1 import lower_match_expression_v1
from .mir_or_return_normalization_v1 import _OrReturnFunctionLowerer
from .mir_variant_constructor_lowering_v1 import (
    lower_payload_free_variant_v1,
    lower_variant_constructor_v1,
)


class _CanonicalFunctionLowererV1(_OrReturnFunctionLowerer):
    def _lower_expression(self, expression: Expression) -> int:
        if isinstance(expression, MatchExpression):
            return lower_match_expression_v1(self, expression)
        if isinstance(expression, CallExpression):
            constructed = lower_variant_constructor_v1(self, expression)
            if constructed is not None:
                return constructed
        if isinstance(expression, Identifier):
            constructed = lower_payload_free_variant_v1(self, expression)
            if constructed is not None:
                return constructed
        return super()._lower_expression(expression)


def lower_function_blocks_v1(declaration, typed_report):
    """Lower one checked function through the canonical executable v4 path."""

    return _CanonicalFunctionLowererV1(declaration, typed_report).lower()


__all__ = ["lower_function_blocks_v1"]
