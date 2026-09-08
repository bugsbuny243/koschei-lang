"""Normalized MIR lowering extensions for Koschei v4.

This module extends the existing MIR lowerer without introducing a second source
semantic authority. It normalizes `or return`, `or else`, supported `or { ... }`
value blocks, short-circuit boolean control flow, interpolated strings, and
staged fail-fast Map/Struct construction while preserving single evaluation and
existing typed-HIR facts.

Stabilized extension instruction class identity lives only in
``mir_extension_instructions_v4``; this lowering module consumes and re-exports
those classes for compatibility but does not redefine them.
"""
from __future__ import annotations

from .ast_nodes import (
    BinaryExpression,
    Block,
    Expression,
    ExpressionStatement,
    ForStatement,
    IfStatement,
    InterpolatedString,
    LetStatement,
    MapLiteral,
    OrBlockExpression,
    OrElseExpression,
    OrReturnExpression,
    ReturnStatement,
    SourceLocation,
    StructLiteral,
    WhileStatement,
)
from .mir_extension_instructions_v4 import (
    MirFallibleIsSuccess,
    MirFalliblePayload,
    MirInterpolate,
    MirIsRuntimeError,
    MirMapFinish,
    MirMapInsert,
    MirMapNew,
    MirStructFinish,
    MirStructNew,
    MirStructSet,
    MirUnit,
)
from .mir_ir import (
    MirBind,
    MirBranch,
    MirJump,
    MirLoad,
    MirReturn,
    MirStore,
    MirUnreachable,
    _FunctionLowerer,
)
from .type_system import BOOL, VOID, TypeNode


class _OrReturnFunctionLowerer(_FunctionLowerer):
    def _new_internal_binding_name(self, purpose: str) -> str:
        while True:
            name = f"$mir_{purpose}_{self.next_binding}"
            self.next_binding += 1
            if name not in self.used_binding_names:
                self.used_binding_names.add(name)
                return name

    def _emit_unit(self, location: SourceLocation) -> int:
        target = self._new_value()
        self._emit(MirUnit(target, VOID, location))
        return target

    def _store_error_or_continue(
        self,
        value: int,
        *,
        result_name: str,
        result_type: TypeNode,
        final_join: int,
        location: SourceLocation,
    ) -> None:
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
            self._emit(MirMapInsert(builder, (key, value), result_type, expression.location))

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
        self._emit(MirStructNew(builder, expression.type_name, result_type, expression.location))
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
            self._emit(MirStructSet(builder, field_name, value, result_type, expression.location))

        finished = self._new_value()
        self._emit(MirStructFinish(finished, builder, result_type, expression.location))
        self._emit(MirStore(result_name, finished, result_type, expression.location))
        self._terminate(MirJump(final_join))

        self.current = final_join
        target = self._new_value()
        self._emit(MirLoad(target, result_name, result_type, expression.location))
        return target

    def _lower_short_circuit(self, expression: BinaryExpression) -> int:
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

    def _lower_or_else(self, expression: OrElseExpression) -> int:
        fallible = self._lower_expression(expression.value)
        success = self._new_value()
        self._emit(MirFallibleIsSuccess(success, fallible, BOOL, expression.location))
        success_block = self._new_block()
        failure_block = self._new_block()
        join_block = self._new_block()
        self._terminate(MirBranch(success, success_block, failure_block))

        result_name = self._new_internal_binding_name("or_else_result")
        result_type = self._type_of(expression)

        self.current = success_block
        payload = self._new_value()
        self._emit(MirFalliblePayload(payload, fallible, result_type, expression.location))
        self._emit(MirBind(result_name, payload, False, result_type, expression.location))
        self._terminate(MirJump(join_block))

        self.current = failure_block
        fallback = self._lower_expression(expression.fallback)
        self._emit(MirBind(result_name, fallback, False, result_type, expression.location))
        self._terminate(MirJump(join_block))

        self.current = join_block
        target = self._new_value()
        self._emit(MirLoad(target, result_name, result_type, expression.location))
        return target

    def _supports_value_block(self, block: Block) -> bool:
        if not block.statements:
            return True
        tail = block.statements[-1]
        if isinstance(tail, (ExpressionStatement, LetStatement, ReturnStatement)):
            return True
        if isinstance(tail, IfStatement):
            if not self._supports_value_block(tail.then_block):
                return False
            if isinstance(tail.else_branch, Block):
                return self._supports_value_block(tail.else_branch)
            if isinstance(tail.else_branch, IfStatement):
                return self._supports_value_if(tail.else_branch)
            return True
        if isinstance(tail, (WhileStatement, ForStatement)):
            return False
        return False

    def _supports_value_if(self, statement: IfStatement) -> bool:
        if not self._supports_value_block(statement.then_block):
            return False
        if isinstance(statement.else_branch, Block):
            return self._supports_value_block(statement.else_branch)
        if isinstance(statement.else_branch, IfStatement):
            return self._supports_value_if(statement.else_branch)
        return True

    def _lower_value_block(
        self,
        block: Block,
        result_type: TypeNode,
        empty_location: SourceLocation,
    ) -> int | None:
        """Lower one expression-valued block and return its normal-exit SSA value.

        Only the final executed statement determines the source block value. Prefix
        statements therefore use ordinary statement lowering; the tail uses the
        value-aware rules below. A function return has no normal block value.
        """

        self.scopes.append({})
        try:
            if not block.statements:
                return self._emit_unit(empty_location)

            for statement in block.statements[:-1]:
                if self.blocks[self.current].terminator is not None:
                    return None
                self._lower_statement(statement)
            if self.blocks[self.current].terminator is not None:
                return None

            tail = block.statements[-1]
            if isinstance(tail, ExpressionStatement):
                return self._lower_expression(tail.expression)
            if isinstance(tail, LetStatement):
                self._lower_statement(tail)
                return self._emit_unit(tail.location)
            if isinstance(tail, ReturnStatement):
                self._lower_statement(tail)
                return None
            if isinstance(tail, IfStatement):
                return self._lower_value_if(tail, result_type)
            raise ValueError(
                "expression-valued MIR block tail is not normalized: "
                f"{type(tail).__name__}"
            )
        finally:
            self.scopes.pop()

    def _lower_value_if(self, statement: IfStatement, result_type: TypeNode) -> int | None:
        condition = self._lower_expression(statement.condition)
        then_block = self._new_block()
        else_block = self._new_block()
        join_block = self._new_block()
        self._terminate(MirBranch(condition, then_block, else_block))
        result_name = self._new_internal_binding_name("value_if_result")

        self.current = then_block
        then_value = self._lower_value_block(
            statement.then_block,
            result_type,
            statement.location,
        )
        then_reaches = (
            then_value is not None and self.blocks[self.current].terminator is None
        )
        if then_reaches:
            self._emit(MirBind(result_name, then_value, False, result_type, statement.location))
            self._terminate(MirJump(join_block))

        self.current = else_block
        if isinstance(statement.else_branch, Block):
            else_value = self._lower_value_block(
                statement.else_branch,
                result_type,
                statement.location,
            )
        elif isinstance(statement.else_branch, IfStatement):
            else_value = self._lower_value_if(statement.else_branch, result_type)
        else:
            else_value = self._emit_unit(statement.location)
        else_reaches = (
            else_value is not None and self.blocks[self.current].terminator is None
        )
        if else_reaches:
            self._emit(MirBind(result_name, else_value, False, result_type, statement.location))
            self._terminate(MirJump(join_block))

        self.current = join_block
        if not then_reaches and not else_reaches:
            self._terminate(MirUnreachable("value-if has no normal exit"))
            return None
        target = self._new_value()
        self._emit(MirLoad(target, result_name, result_type, statement.location))
        return target

    def _lower_or_block(self, expression: OrBlockExpression) -> int:
        fallible = self._lower_expression(expression.value)
        success = self._new_value()
        self._emit(MirFallibleIsSuccess(success, fallible, BOOL, expression.location))
        success_block = self._new_block()
        failure_block = self._new_block()
        join_block = self._new_block()
        self._terminate(MirBranch(success, success_block, failure_block))

        result_name = self._new_internal_binding_name("or_block_result")
        result_type = self._type_of(expression)

        self.current = success_block
        payload = self._new_value()
        self._emit(MirFalliblePayload(payload, fallible, result_type, expression.location))
        self._emit(MirBind(result_name, payload, False, result_type, expression.location))
        self._terminate(MirJump(join_block))

        self.current = failure_block
        handler_value = self._lower_value_block(
            expression.handler,
            result_type,
            expression.location,
        )
        if handler_value is not None and self.blocks[self.current].terminator is None:
            self._emit(
                MirBind(
                    result_name,
                    handler_value,
                    False,
                    result_type,
                    expression.location,
                )
            )
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
        if isinstance(expression, BinaryExpression) and expression.operator in {"&&", "||"}:
            return self._lower_short_circuit(expression)
        if isinstance(expression, InterpolatedString):
            items = tuple(self._lower_expression(part) for part in expression.parts)
            target = self._new_value()
            self._emit(MirInterpolate(target, items, self._type_of(expression), expression.location))
            return target
        if isinstance(expression, OrElseExpression):
            return self._lower_or_else(expression)
        if isinstance(expression, OrBlockExpression):
            if self._supports_value_block(expression.handler):
                return self._lower_or_block(expression)
            return super()._lower_expression(expression)
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
        failure_value = fallible if expression.error is None else self._lower_expression(expression.error)
        self._terminate(MirReturn(failure_value))

        self.current = success_block
        payload = self._new_value()
        self._emit(MirFalliblePayload(payload, fallible, self._type_of(expression), expression.location))
        self._terminate(MirJump(join_block))
        self.current = join_block
        return payload


def lower_function_blocks_v1(declaration, typed_report):
    return _OrReturnFunctionLowerer(declaration, typed_report).lower()


__all__ = [
    "MirFallibleIsSuccess",
    "MirFalliblePayload",
    "MirInterpolate",
    "lower_function_blocks_v1",
]
