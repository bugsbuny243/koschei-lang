"""Normalized MIR lowering for Koschei `or return` semantics v1.

This module deliberately extends the existing MIR lowerer without introducing a
second source semantic authority.  `OrReturnExpression` is lowered into one
fallible value, one explicit success predicate, and CFG success/failure paths.
The inner expression is therefore emitted exactly once.

Runtime execution of these instructions is a separate convergence step.  Until
the MIR execution boundary consumes them directly, this module is a compiler
normalization prototype and must not be described as end-to-end runtime proof.
"""
from __future__ import annotations

from dataclasses import dataclass

from .ast_nodes import Expression, OrReturnExpression, SourceLocation
from .mir_ir import (
    MirBranch,
    MirJump,
    MirReturn,
    _FunctionLowerer,
)
from .type_system import BOOL, TypeNode


@dataclass(frozen=True, slots=True)
class MirFallibleIsSuccess:
    """Return Bool truth for Koschei fallible-unwrapping semantics."""

    target: int
    source: int
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirFalliblePayload:
    """Extract the success payload; valid only on a proven-success CFG path."""

    target: int
    source: int
    type: TypeNode
    location: SourceLocation


class _OrReturnFunctionLowerer(_FunctionLowerer):
    def _lower_expression(self, expression: Expression) -> int:
        if not isinstance(expression, OrReturnExpression):
            return super()._lower_expression(expression)

        # Evaluate the effectful/fallible expression exactly once.  In
        # particular, a nested capability call becomes the ordinary normalized
        # MirMember -> MirCall chain before control flow is split.
        fallible = super()._lower_expression(expression.value)

        success = self._new_value()
        self._emit(
            MirFallibleIsSuccess(
                success,
                fallible,
                BOOL,
                expression.location,
            )
        )

        success_block = self._new_block()
        failure_block = self._new_block()
        join_block = self._new_block()
        self._terminate(MirBranch(success, success_block, failure_block))

        # Failure preserves the original value, unless source explicitly asks
        # for a replacement.  Replacement evaluation is failure-only.
        self.current = failure_block
        failure_value = (
            fallible
            if expression.error is None
            else self._lower_expression(expression.error)
        )
        self._terminate(MirReturn(failure_value))

        # Payload extraction is reachable only after the success predicate.
        self.current = success_block
        payload = self._new_value()
        self._emit(
            MirFalliblePayload(
                payload,
                fallible,
                self._type_of(expression),
                expression.location,
            )
        )
        self._terminate(MirJump(join_block))

        self.current = join_block
        return payload


def lower_function_blocks_v1(declaration, typed_report):
    """Lower one checked function with normalized `or return` CFG semantics."""

    return _OrReturnFunctionLowerer(declaration, typed_report).lower()
