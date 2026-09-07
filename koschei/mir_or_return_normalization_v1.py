"""Normalized MIR lowering extensions for Koschei v4.

This module extends the existing MIR lowerer without introducing a second source
semantic authority. It normalizes `or return`, short-circuit boolean control
flow, interpolated strings, and staged fail-fast Map/Struct construction while
preserving single evaluation and existing typed-HIR facts.
"""
from __future__ import annotations

from dataclasses import dataclass

from .ast_nodes import (
    BinaryExpression,
    Expression,
    InterpolatedString,
    MapLiteral,
    OrReturnExpression,
    SourceLocation,
    StructLiteral,
)
from .mir_container_staging_v1 import (
    MirIsRuntimeError,
    MirMapFinish,
    MirMapInsert,
    MirMapNew,
    MirStructFinish,
    MirStructNew,
    MirStructSet,
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

    def _store_error_or_continue(
        self,
        value: int,
        *,
        result_name: str,
        result_type: TypeNode,
        final_join: int,
        location: SourceLocation,
    ) -> None:
        """Branch on KsError without conflating Result/Option fallibility.

        The error path stores the exact error value as the surrounding container
        expression result and jumps to the final join. The success path becomes
        the new current block, so later source expressions are unreachable after
        an earlier error.
        """

        is_error = self._new_value()
        self._emit(MirIsRuntimeError(is_error, value, BOOL, location))
        error_block = self._new_block()
        continue_block = self._new_block()
        self._terminate(MirBranch(is_error, error_block, continue_block))

        self.current = error_block
        self._emit(MirStore(result_name, value, result_type, location))
        self._terminate(MirJump(final_join))

        self.current = continue_block

    def _lower_map_literal(self, expression: MapLiteral) -> int:
        result_type = self._type_of(expression)
        builder = self._new_value()
        self._emit(MirMapNew(builder, result_type, expression.location))

        result_name = self._new_internal_binding_name("map_result")
        self._emit(MirBind(result_name, builder, True, result_type, expression.location))
        final_join = self._new_block()

        for key_expression, value_expression in expression.entries:
            key = self._lower_expression(key_expression)
            self._store_error_or_continue(
                key,
                result_name=result_name,
                result_type=result_type,
                final_join=final_join,
                location=key_expression.location,
            )

            value = self._lower_expression(value_expression)
            self._store_error_or_continue(
                value,
                result_name=result_name,
                result_type=result_type,
                final_join=final_join,
                location=value_expression.location,
            )

            self._emit(
                MirMapInsert(
                    builder,
                    key,
                    value,
                    result_type,
                    expression.location,
                )
            )

        finished = self._new_value()
        self._emit(MirMapFinish(finished, builder, result_type, expression.location))
        self._emit(MirStore(result_name, finished, result_type, expression.location))
        self._terminate(MirJump(final_join))

        self.current = final_join
        target = self._new_value()
        self._emit(MirLoad(target, result_name, result_type, expression.location))
        return target

    def _lower_struct_literal(self, expression: StructLiteral) -> int:
        result_type = self._type_of(expression)
        builder = self._new_value()
        self._emit(
            MirStructNew(
                builder,
                expression.type_name,
                result_type,
                expression.location,
            )
        )

        result_name = self._new_internal_binding_name("struct_result")
        self._emit(MirBind(result_name, builder, True, result_type, expression.location))
        final_join = self._new_block()

        for field_name, value_expression in expression.fields:
            value = self._lower_expression(value_expression)
            self._store_error_or_continue(
                value,
                result_name=result_name,
                result_type=result_type,
                final_join=final_join,
                location=value_expression.location,
            )
            self._emit(
                MirStructSet(
                    builder,
                    field_name,
                    value,
                    result_type,
                    expression.location,
                )
            )

        finished = self._new_value()
        self._emit(MirStructFinish(finished, builder, result_type, expression.location))
        self._emit(MirStore(result_name, finished, result_type, expression.location))
        self._terminate(MirJump(final_join))

        self.current = final_join
        target = self._new_value()
        self._emit(MirLoad(target, result_name, result_type, expression.location))
        return target

    def _lower_short_circuit(self, expression: BinaryExpression) -> int:
        """Lower && / || so the RHS is reachable only when source semantics require it."""

        left = self._lower_expression(expression.left)
        result_name = self._new_internal_binding_name("shortcircuit")
        result_type = self._type_of(expression)
        self._emit(MirBind(result_name, left, True, result_type, expression.location))

        rhs_block = self._new_block()
        skip_block = self._new_block()
        join_block = self._new_block()

        if expression.operator == "&&":
            self._terminate(MirBranch(left, rhs_block, skip_block))
        else:
            self._terminate(MirBranch(left, skip_block, rhs_block))

        self.current = rhs_block
        right = self._lower_expression(expression.right)
        self._emit(MirStore(result_name, right, result_type, expression.location))
        self._terminate(MirJump(join_block))

        self.current = skip_block
        self._terminate(MirJump(join_block))

        self.current = join_block
        target = self._new_value()
        self._emit(MirLoad(target, result_name, result_type, expression.location))
        return target

    def _lower_expression(self, expression: Expression) -> int:
        if isinstance(expression, MapLiteral):
            return self._lower_map_literal(expression)

        if isinstance(expression, StructLiteral):
            return self._lower_struct_literal(expression)

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

        fallible = self._lower_expression(expression.value)
        success = self._new_value()
        self._emit(MirFallibleIsSuccess(success, fallible, BOOL, expression.location))

        success_block = self._new_block()
        failure_block = self._new_block()
        join_block = self._new_block()
        self._terminate(MirBranch(success, success_block, failure_block))

        self.current = failure_block
        failure_value = (
            fallible
            if expression.error is None
            else self._lower_expression(expression.error)
        )
        self._terminate(MirReturn(failure_value))

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
