"""Normalized MIR lowering extensions for Koschei v4."""
from __future__ import annotations

from ._typed_expr import checked_block_normal_type
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
    MirAstFallback,
    MirBind,
    MirBranch,
    MirIterHasNext,
    MirIterInit,
    MirIterNext,
    MirJump,
    MirLoad,
    MirReturn,
    MirStore,
    _FunctionLowerer,
)
from .type_system import BOOL, STRING, VOID, GenericType, TypeNode, UnknownType
from .typed_hir import iterable_success_item_type


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

    def _lower_if(self, statement: IfStatement) -> None:
        condition = self._lower_expression(statement.condition)
        is_error = self._new_value()
        self._emit(MirIsRuntimeError(is_error, condition, BOOL, statement.location))
        error_block = self._new_block()
        decision_block = self._new_block()
        then_block = self._new_block()
        else_block = self._new_block()
        join_block = self._new_block()
        self._terminate(MirBranch(is_error, error_block, decision_block))
        self.current = error_block
        self._terminate(MirJump(join_block))
        self.current = decision_block
        self._terminate(MirBranch(condition, then_block, else_block))
        self.current = then_block
        self._lower_block(statement.then_block)
        if self.blocks[self.current].terminator is None:
            self._terminate(MirJump(join_block))
        self.current = else_block
        if isinstance(statement.else_branch, Block):
            self._lower_block(statement.else_branch)
        elif isinstance(statement.else_branch, IfStatement):
            self._lower_if(statement.else_branch)
        if self.blocks[self.current].terminator is None:
            self._terminate(MirJump(join_block))
        self.current = join_block

    def _lower_while(self, statement: WhileStatement) -> None:
        """Preserve condition and body Error results as loop-statement completion."""

        if not self._supports_value_block(statement.body):
            self._emit(
                MirAstFallback(
                    None,
                    type(statement).__name__,
                    UnknownType(),
                    statement.location,
                )
            )
            return

        body_type = checked_block_normal_type(self.typed_report, statement.body)
        condition_block = self._new_block()
        condition_error_block = self._new_block()
        decision_block = self._new_block()
        body_block = self._new_block()
        exit_block = self._new_block()
        self._terminate(MirJump(condition_block))

        self.current = condition_block
        condition = self._lower_expression(statement.condition)
        condition_is_error = self._new_value()
        self._emit(
            MirIsRuntimeError(
                condition_is_error,
                condition,
                BOOL,
                statement.location,
            )
        )
        self._terminate(
            MirBranch(condition_is_error, condition_error_block, decision_block)
        )

        self.current = condition_error_block
        self._terminate(MirJump(exit_block))

        self.current = decision_block
        self._terminate(MirBranch(condition, body_block, exit_block))

        self.current = body_block
        self.loop_targets.append((exit_block, condition_block))
        try:
            body_value = self._lower_value_block(
                statement.body,
                statement.location,
                body_type,
            )
        finally:
            self.loop_targets.pop()

        if body_value is not None and self.blocks[self.current].terminator is None:
            body_is_error = self._new_value()
            self._emit(
                MirIsRuntimeError(
                    body_is_error,
                    body_value,
                    BOOL,
                    statement.location,
                )
            )
            body_error_block = self._new_block()
            continue_block = self._new_block()
            self._terminate(MirBranch(body_is_error, body_error_block, continue_block))
            self.current = body_error_block
            self._terminate(MirJump(exit_block))
            self.current = continue_block
            self._terminate(MirJump(condition_block))

        self.current = exit_block

    def _lower_for(self, statement: ForStatement) -> None:
        """Normalize iterable/body Error completion from checked Typed-HIR facts."""

        iterable_type = self._type_of(statement.iterable)
        item_type = iterable_success_item_type(iterable_type)
        if item_type is None or not self._supports_value_block(statement.body):
            self._emit(
                MirAstFallback(
                    None,
                    type(statement).__name__,
                    UnknownType(),
                    statement.location,
                )
            )
            return

        body_type = checked_block_normal_type(self.typed_report, statement.body)
        iterable = self._lower_expression(statement.iterable)
        iterable_is_error = self._new_value()
        self._emit(
            MirIsRuntimeError(
                iterable_is_error,
                iterable,
                BOOL,
                statement.location,
            )
        )
        iterable_error_block = self._new_block()
        iterator_init_block = self._new_block()
        condition_block = self._new_block()
        body_block = self._new_block()
        exit_block = self._new_block()
        self._terminate(
            MirBranch(iterable_is_error, iterable_error_block, iterator_init_block)
        )

        self.current = iterable_error_block
        self._terminate(MirJump(exit_block))

        self.current = iterator_init_block
        iterator = self._new_value()
        self._emit(
            MirIterInit(
                iterator,
                iterable,
                GenericType("Iterator", (item_type,)),
                statement.location,
            )
        )
        self._terminate(MirJump(condition_block))

        self.current = condition_block
        has_next = self._new_value()
        self._emit(MirIterHasNext(has_next, iterator, BOOL, statement.location))
        self._terminate(MirBranch(has_next, body_block, exit_block))

        self.current = body_block
        self.scopes.append({})
        self.loop_targets.append((exit_block, condition_block))
        try:
            item = self._new_value()
            self._emit(MirIterNext(item, iterator, item_type, statement.location))
            binding_name = self._new_binding_name(statement.variable)
            self._emit(
                MirBind(
                    binding_name,
                    item,
                    False,
                    item_type,
                    statement.location,
                )
            )
            body_value = self._lower_value_block(
                statement.body,
                statement.location,
                body_type,
            )
        finally:
            self.loop_targets.pop()
            self.scopes.pop()

        if body_value is not None and self.blocks[self.current].terminator is None:
            body_is_error = self._new_value()
            self._emit(
                MirIsRuntimeError(
                    body_is_error,
                    body_value,
                    BOOL,
                    statement.location,
                )
            )
            body_error_block = self._new_block()
            continue_block = self._new_block()
            self._terminate(MirBranch(body_is_error, body_error_block, continue_block))
            self.current = body_error_block
            self._terminate(MirJump(exit_block))
            self.current = continue_block
            self._terminate(MirJump(condition_block))

        self.current = exit_block

    def _lower_map_literal(self, expression: MapLiteral) -> int:
        result_type = self._type_of(expression)
        resolution = self.typed_report.map_literal_resolution_of(expression)
        if resolution is None:
            raise ValueError("map literal requires canonical Typed-HIR resolution")
        if resolution.key_type != STRING or resolution.duplicate_policy != "reject":
            raise ValueError("unsupported canonical Map literal contract")
        builder = self._new_value()
        self._emit(MirMapNew(builder, result_type, expression.location))
        result_name = self._new_internal_binding_name("map_result")
        self._emit(MirBind(result_name, builder, True, result_type, expression.location))
        final_join = self._new_block()
        for key_expression, value_expression in expression.entries:
            key = self._lower_expression(key_expression)
            self._store_error_or_continue(key, result_name=result_name, result_type=result_type, final_join=final_join, location=key_expression.location)
            value = self._lower_expression(value_expression)
            self._store_error_or_continue(value, result_name=result_name, result_type=result_type, final_join=final_join, location=value_expression.location)
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
        resolution = self.typed_report.struct_literal_resolution_of(expression)
        if resolution is None:
            raise ValueError("struct literal requires canonical Typed-HIR resolution")
        builder = self._new_value()
        self._emit(
            MirStructNew(
                builder,
                resolution.type_name,
                resolution.required_fields,
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
        left = self._lower_expression(expression.left)
        result_name = self._new_internal_binding_name("shortcircuit")
        result_type = self._type_of(expression)
        self._emit(MirBind(result_name, left, True, result_type, expression.location))
        is_error = self._new_value()
        self._emit(MirIsRuntimeError(is_error, left, BOOL, expression.location))
        decision_block = self._new_block()
        rhs_block = self._new_block()
        skip_block = self._new_block()
        join_block = self._new_block()
        self._terminate(MirBranch(is_error, join_block, decision_block))
        self.current = decision_block
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

    @classmethod
    def _supports_value_if(cls, statement: IfStatement) -> bool:
        if not cls._supports_value_block(statement.then_block):
            return False
        if isinstance(statement.else_branch, Block):
            return cls._supports_value_block(statement.else_branch)
        if isinstance(statement.else_branch, IfStatement):
            return cls._supports_value_if(statement.else_branch)
        return True

    @classmethod
    def _supports_value_block(cls, block: Block) -> bool:
        for statement in block.statements:
            if isinstance(statement, ReturnStatement):
                return True
            if isinstance(statement, (ExpressionStatement, LetStatement)):
                continue
            if isinstance(statement, IfStatement) and cls._supports_value_if(statement):
                continue
            if isinstance(statement, WhileStatement) and cls._supports_value_block(statement.body):
                continue
            if isinstance(statement, ForStatement) and cls._supports_value_block(statement.body):
                continue
            return False
        return True

    def _lower_value_if(self, statement: IfStatement, result_type: TypeNode) -> int | None:
        condition = self._lower_expression(statement.condition)
        is_error = self._new_value()
        self._emit(MirIsRuntimeError(is_error, condition, BOOL, statement.location))
        error_block = self._new_block()
        decision_block = self._new_block()
        then_block = self._new_block()
        else_block = self._new_block()
        join_block = self._new_block()
        result_name = self._new_internal_binding_name("value_if_result")
        self._terminate(MirBranch(is_error, error_block, decision_block))
        self.current = error_block
        self._emit(MirBind(result_name, condition, False, result_type, statement.location))
        self._terminate(MirJump(join_block))
        self.current = decision_block
        self._terminate(MirBranch(condition, then_block, else_block))
        self.current = then_block
        then_value = self._lower_value_block(statement.then_block, statement.location, result_type)
        if then_value is not None and self.blocks[self.current].terminator is None:
            self._emit(MirBind(result_name, then_value, False, result_type, statement.location))
            self._terminate(MirJump(join_block))
        self.current = else_block
        if isinstance(statement.else_branch, Block):
            else_value = self._lower_value_block(statement.else_branch, statement.location, result_type)
        elif isinstance(statement.else_branch, IfStatement):
            else_value = self._lower_value_if(statement.else_branch, result_type)
        else:
            else_value = self._emit_unit(statement.location)
        if else_value is not None and self.blocks[self.current].terminator is None:
            self._emit(MirBind(result_name, else_value, False, result_type, statement.location))
            self._terminate(MirJump(join_block))
        self.current = join_block
        target = self._new_value()
        self._emit(MirLoad(target, result_name, result_type, statement.location))
        return target

    def _lower_value_while(self, statement: WhileStatement, result_type: TypeNode) -> int | None:
        """Lower a while statement whose statement value is consumed by a block."""

        body_type = checked_block_normal_type(self.typed_report, statement.body)
        initial = self._emit_unit(statement.location)
        result_name = self._new_internal_binding_name("value_while_result")
        self._emit(MirBind(result_name, initial, True, result_type, statement.location))

        condition_block = self._new_block()
        condition_error_block = self._new_block()
        decision_block = self._new_block()
        body_block = self._new_block()
        final_join = self._new_block()
        self._terminate(MirJump(condition_block))

        self.current = condition_block
        condition = self._lower_expression(statement.condition)
        condition_is_error = self._new_value()
        self._emit(MirIsRuntimeError(condition_is_error, condition, BOOL, statement.location))
        self._terminate(MirBranch(condition_is_error, condition_error_block, decision_block))

        self.current = condition_error_block
        self._emit(MirStore(result_name, condition, result_type, statement.location))
        self._terminate(MirJump(final_join))

        self.current = decision_block
        self._terminate(MirBranch(condition, body_block, final_join))

        self.current = body_block
        self.loop_targets.append((final_join, condition_block))
        try:
            body_value = self._lower_value_block(statement.body, statement.location, body_type)
        finally:
            self.loop_targets.pop()

        if body_value is not None and self.blocks[self.current].terminator is None:
            self._emit(MirStore(result_name, body_value, result_type, statement.location))
            body_is_error = self._new_value()
            self._emit(MirIsRuntimeError(body_is_error, body_value, BOOL, statement.location))
            body_error_block = self._new_block()
            continue_block = self._new_block()
            self._terminate(MirBranch(body_is_error, body_error_block, continue_block))
            self.current = body_error_block
            self._terminate(MirJump(final_join))
            self.current = continue_block
            self._terminate(MirJump(condition_block))

        self.current = final_join
        target = self._new_value()
        self._emit(MirLoad(target, result_name, result_type, statement.location))
        return target

    def _lower_value_for(self, statement: ForStatement, result_type: TypeNode) -> int | None:
        """Lower a for statement whose statement value is consumed by a block."""

        iterable_type = self._type_of(statement.iterable)
        item_type = iterable_success_item_type(iterable_type)
        if item_type is None:
            raise ValueError("value-position for requires a checked List iterable")

        body_type = checked_block_normal_type(self.typed_report, statement.body)
        initial = self._emit_unit(statement.location)
        result_name = self._new_internal_binding_name("value_for_result")
        self._emit(MirBind(result_name, initial, True, result_type, statement.location))

        iterable = self._lower_expression(statement.iterable)
        iterable_is_error = self._new_value()
        self._emit(MirIsRuntimeError(iterable_is_error, iterable, BOOL, statement.location))
        iterable_error_block = self._new_block()
        iterator_init_block = self._new_block()
        condition_block = self._new_block()
        body_block = self._new_block()
        final_join = self._new_block()
        self._terminate(MirBranch(iterable_is_error, iterable_error_block, iterator_init_block))

        self.current = iterable_error_block
        self._emit(MirStore(result_name, iterable, result_type, statement.location))
        self._terminate(MirJump(final_join))

        self.current = iterator_init_block
        iterator = self._new_value()
        self._emit(
            MirIterInit(
                iterator,
                iterable,
                GenericType("Iterator", (item_type,)),
                statement.location,
            )
        )
        self._terminate(MirJump(condition_block))

        self.current = condition_block
        has_next = self._new_value()
        self._emit(MirIterHasNext(has_next, iterator, BOOL, statement.location))
        self._terminate(MirBranch(has_next, body_block, final_join))

        self.current = body_block
        self.scopes.append({})
        self.loop_targets.append((final_join, condition_block))
        try:
            item = self._new_value()
            self._emit(MirIterNext(item, iterator, item_type, statement.location))
            binding_name = self._new_binding_name(statement.variable)
            self._emit(MirBind(binding_name, item, False, item_type, statement.location))
            body_value = self._lower_value_block(statement.body, statement.location, body_type)
        finally:
            self.loop_targets.pop()
            self.scopes.pop()

        if body_value is not None and self.blocks[self.current].terminator is None:
            self._emit(MirStore(result_name, body_value, result_type, statement.location))
            body_is_error = self._new_value()
            self._emit(MirIsRuntimeError(body_is_error, body_value, BOOL, statement.location))
            body_error_block = self._new_block()
            continue_block = self._new_block()
            self._terminate(MirBranch(body_is_error, body_error_block, continue_block))
            self.current = body_error_block
            self._terminate(MirJump(final_join))
            self.current = continue_block
            self._terminate(MirJump(condition_block))

        self.current = final_join
        target = self._new_value()
        self._emit(MirLoad(target, result_name, result_type, statement.location))
        return target

    def _lower_value_block(self, block: Block, empty_location: SourceLocation, result_type: TypeNode | None = None) -> int | None:
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
                if result_type is None:
                    raise ValueError("value-position if requires canonical result type")
                return self._lower_value_if(tail, result_type)
            if isinstance(tail, WhileStatement):
                if result_type is None:
                    raise ValueError("value-position while requires canonical result type")
                return self._lower_value_while(tail, result_type)
            if isinstance(tail, ForStatement):
                if result_type is None:
                    raise ValueError("value-position for requires canonical result type")
                return self._lower_value_for(tail, result_type)
            raise ValueError(f"proven value-block admission drifted: {type(tail).__name__}")
        finally:
            self.scopes.pop()

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
        handler_value = self._lower_value_block(expression.handler, expression.location, result_type)
        if handler_value is not None and self.blocks[self.current].terminator is None:
            self._emit(MirBind(result_name, handler_value, False, result_type, expression.location))
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


__all__ = ["MirFallibleIsSuccess", "MirFalliblePayload", "MirInterpolate", "lower_function_blocks_v1"]