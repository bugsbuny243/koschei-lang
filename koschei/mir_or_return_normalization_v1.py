"""Normalized MIR lowering extensions for Koschei v4.

This module extends the existing MIR lowerer without introducing a second source
semantic authority. It currently normalizes `or return`, short-circuit boolean
control flow, and interpolated strings while preserving single evaluation and
existing typed-HIR facts.

The public checked runtime consumes these MIR v4 instructions directly via
MirExecutorV1. Native/backend convergence is still incomplete, so this module
must not be described as proof that every backend consumes identical semantics.
"""
from __future__ import annotations

from dataclasses import dataclass

from .ast_nodes import (
    BinaryExpression,
    Expression,
    InterpolatedString,
    OrReturnExpression,
    SourceLocation,
)
from .mir_ir import (
    MirBind,
    MirBranch,
    MirJump,
    MirLoad,
    MirReturn,
    MirStore,
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


@dataclass(frozen=True, slots=True)
class MirInterpolate:
    """Join canonical string projections of already-evaluated MIR values."""

    target: int
    items: tuple[int, ...]
    type: TypeNode
    location: SourceLocation


class _OrReturnFunctionLowerer(_FunctionLowerer):
    def _new_internal_binding_name(self, purpose: str) -> str:
        """Allocate a compiler-only binding without altering source scope lookup."""

        while True:
            name = f"$mir_{purpose}_{self.next_binding}"
            self.next_binding += 1
            if name not in self.used_binding_names:
                self.used_binding_names.add(name)
                return name

    def _lower_short_circuit(self, expression: BinaryExpression) -> int:
        """Lower && / || so the RHS is reachable only when source semantics require it."""

        left = self._lower_expression(expression.left)
        result_name = self._new_internal_binding_name("shortcircuit")
        result_type = self._type_of(expression)
        self._emit(
            MirBind(
                result_name,
                left,
                True,
                result_type,
                expression.location,
            )
        )

        rhs_block = self._new_block()
        skip_block = self._new_block()
        join_block = self._new_block()

        if expression.operator == "&&":
            self._terminate(MirBranch(left, rhs_block, skip_block))
        else:
            self._terminate(MirBranch(left, skip_block, rhs_block))

        self.current = rhs_block
        right = self._lower_expression(expression.right)
        self._emit(
            MirStore(
                result_name,
                right,
                result_type,
                expression.location,
            )
        )
        self._terminate(MirJump(join_block))

        self.current = skip_block
        self._terminate(MirJump(join_block))

        self.current = join_block
        target = self._new_value()
        self._emit(
            MirLoad(
                target,
                result_name,
                result_type,
                expression.location,
            )
        )
        return target

    def _lower_expression(self, expression: Expression) -> int:
        if (
            isinstance(expression, BinaryExpression)
            and expression.operator in {"&&", "||"}
        ):
            return self._lower_short_circuit(expression)

        if isinstance(expression, InterpolatedString):
            items = tuple(self._lower_expression(part) for part in expression.parts)
            target = self._new_value()
            self._emit(
                MirInterpolate(
                    target,
                    items,
                    self._type_of(expression),
                    expression.location,
                )
            )
            return target

        if not isinstance(expression, OrReturnExpression):
            return super()._lower_expression(expression)

        # Evaluate the effectful/fallible expression exactly once. In
        # particular, a nested capability call becomes the ordinary normalized
        # MirMember -> MirCall chain before control flow is split.
        fallible = self._lower_expression(expression.value)

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
        # for a replacement. Replacement evaluation is failure-only.
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
    """Lower one checked function with Koschei MIR v4 extension semantics."""

    return _OrReturnFunctionLowerer(declaration, typed_report).lower()
