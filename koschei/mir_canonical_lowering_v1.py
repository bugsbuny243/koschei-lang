"""Canonical executable MIR v4 lowering entry-point.

This module is the explicit bridge from the normalized v4 lowerer to
compiler-owned MatchExpression lowering.  It creates no second semantic
authority: match owner, payload type, arm order and exhaustiveness come only
from Typed-HIR through ``lower_match_expression_v1``.
"""
from __future__ import annotations

from .ast_nodes import Expression, MatchExpression
from .mir_match_lowering_v1 import lower_match_expression_v1
from .mir_or_return_normalization_v1 import _OrReturnFunctionLowerer


class _CanonicalFunctionLowererV1(_OrReturnFunctionLowerer):
    def _lower_expression(self, expression: Expression) -> int:
        if isinstance(expression, MatchExpression):
            return lower_match_expression_v1(self, expression)
        return super()._lower_expression(expression)


def lower_function_blocks_v1(declaration, typed_report):
    """Lower one checked function through the canonical executable v4 path."""

    return _CanonicalFunctionLowererV1(declaration, typed_report).lower()


__all__ = ["lower_function_blocks_v1"]
