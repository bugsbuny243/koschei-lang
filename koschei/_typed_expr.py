"""Expression lowering for the V5 Typed HIR migration pass."""

from __future__ import annotations

from ._typed_ops import binary_type, method_type
from .ast_nodes import (
    AssignmentExpression,
    BinaryExpression,
    Block,
    CallExpression,
    ExpressionStatement,
    ForStatement,
    Identifier,
    IfStatement,
    InterpolatedString,
    LetStatement,
    ListLiteral,
    Literal,
    MapLiteral,
    MatchExpression,
    MemberExpression,
    OrBlockExpression,
    OrElseExpression,
    OrReturnExpression,
    ReturnStatement,
    StructLiteral,
    UnaryExpression,
    WhileStatement,
)
from .type_system import (
    BOOL,
    ERROR,
    FLOAT,
    INT,
    STRING,
    UNKNOWN,
    VOID,
    NamedType,
    UnknownType,
    alternatives,
    generic,
    success_type,
    union_type,
)


def _recorded_expression_type(checked_facts, expression):
    """Read an already-checked Typed-HIR expression fact by object identity."""

    for item in reversed(checked_facts.expressions):
        if item.expression is expression:
            return item.type
    return UNKNOWN


def _error_result_type(type_node):
    """Project the canonical Error alternative without re-running inference."""

    return ERROR if any(option == ERROR for option in alternatives(type_node)) else None


def _checked_statement_normal_type(checked_facts, statement):
    """Project normal-exit statement value from already-checked Typed-HIR facts.

    ``None`` means the statement has no normal continuation (an explicit
    function return). This function never calls ``infer`` and therefore cannot
    become a second expression-type authority.
    """

    if isinstance(statement, LetStatement):
        return VOID
    if isinstance(statement, ReturnStatement):
        return None
    if isinstance(statement, ExpressionStatement):
        return _recorded_expression_type(checked_facts, statement.expression)
    if isinstance(statement, IfStatement):
        normal_types = []
        condition_error = _error_result_type(
            _recorded_expression_type(checked_facts, statement.condition)
        )
        if condition_error is not None:
            normal_types.append(condition_error)
        then_type = checked_block_normal_type(checked_facts, statement.then_block)
        if then_type is not None:
            normal_types.append(then_type)
        if isinstance(statement.else_branch, Block):
            else_type = checked_block_normal_type(checked_facts, statement.else_branch)
        elif isinstance(statement.else_branch, IfStatement):
            else_type = _checked_statement_normal_type(checked_facts, statement.else_branch)
        else:
            else_type = VOID
        if else_type is not None:
            normal_types.append(else_type)
        return union_type(*normal_types) if normal_types else None
    if isinstance(statement, WhileStatement):
        normal_types = [VOID]
        condition_error = _error_result_type(
            _recorded_expression_type(checked_facts, statement.condition)
        )
        if condition_error is not None:
            normal_types.append(condition_error)
        body_type = checked_block_normal_type(checked_facts, statement.body)
        if body_type is not None:
            normal_types.append(body_type)
        return union_type(*normal_types)
    if isinstance(statement, ForStatement):
        normal_types = [VOID]
        iterable_error = _error_result_type(
            _recorded_expression_type(checked_facts, statement.iterable)
        )
        if iterable_error is not None:
            normal_types.append(iterable_error)
        body_type = checked_block_normal_type(checked_facts, statement.body)
        if body_type is not None:
            normal_types.append(body_type)
        return union_type(*normal_types)
    return UNKNOWN


def checked_block_normal_type(checked_facts, block: Block):
    """Canonical normal-exit value type projected only from checked HIR facts."""

    normal_type = VOID
    can_continue = True
    for statement in block.statements:
        statement_type = _checked_statement_normal_type(checked_facts, statement)
        if not can_continue:
            continue
        if statement_type is None:
            can_continue = False
        else:
            normal_type = statement_type
    return normal_type if can_continue else None


def infer_expression(checker, expression):
    if isinstance(expression, Literal):
        if isinstance(expression.value, bool):
            return checker.record(expression, BOOL)
        if isinstance(expression.value, str):
            return checker.record(expression, STRING)
        if isinstance(expression.value, int):
            return checker.record(expression, INT)
        if isinstance(expression.value, float):
            return checker.record(expression, FLOAT)
        return checker.record(expression, UNKNOWN)

    if isinstance(expression, InterpolatedString):
        for part in expression.parts:
            checker.infer(part)
        return checker.record(expression, STRING)

    if isinstance(expression, ListLiteral):
        checker.collections += 1
        item_type = union_type(*(checker.infer(item) for item in expression.items))
        return checker.record(expression, generic("List", item_type))

    if isinstance(expression, MapLiteral):
        checker.collections += 1
        values = union_type(*(checker.infer(value) for _, value in expression.entries))
        for key, _ in expression.entries:
            checker.infer(key)
        return checker.record(expression, generic("Map", STRING, values))

    if isinstance(expression, StructLiteral):
        return checker.record(expression, checker.struct_literal_type(expression))

    if isinstance(expression, Identifier):
        local = checker.resolve(expression.name)
        if not isinstance(local, UnknownType):
            return checker.record(expression, local)
        function = checker.functions.get(expression.name)
        if function is not None:
            from .type_contracts import function_type

            return checker.record(
                expression, function_type(function, function.return_type)
            )
        if expression.name in checker.imports:
            return checker.record(expression, NamedType(f"Module:{expression.name}"))
        variant = checker.variants.get(expression.name)
        if variant is not None:
            return checker.record(expression, NamedType(variant[0]))
        return checker.record(expression, UNKNOWN)

    if isinstance(expression, MemberExpression):
        receiver = checker.infer(expression.object)
        return checker.record(
            expression, checker.field_type(receiver, expression.member) or receiver
        )

    if isinstance(expression, CallExpression):
        arguments = tuple(checker.infer(item) for item in expression.arguments)
        if isinstance(expression.callee, MemberExpression):
            receiver = checker.infer(expression.callee.object)
            module_result = checker.module_call_type(
                receiver,
                expression.callee.member,
                arguments,
                expression.location,
            )
            result = module_result if module_result is not None else method_type(
                receiver, expression.callee.member, arguments, expression.location
            )
            return checker.record(expression, result)
        if isinstance(expression.callee, Identifier):
            return checker.record(
                expression,
                checker.call_type(
                    expression.callee.name, arguments, expression.location
                ),
            )
        checker.infer(expression.callee)
        return checker.record(expression, UNKNOWN)

    if isinstance(expression, BinaryExpression):
        return checker.record(
            expression,
            binary_type(
                checker.infer(expression.left),
                expression.operator,
                checker.infer(expression.right),
                expression.location,
            ),
        )

    if isinstance(expression, UnaryExpression):
        operand = checker.infer(expression.operand)
        return checker.record(expression, BOOL if expression.operator == "!" else operand)

    if isinstance(expression, OrReturnExpression):
        narrowed = success_type(checker.infer(expression.value))
        if expression.error is not None:
            checker.infer(expression.error)
        return checker.record(expression, narrowed)

    if isinstance(expression, OrElseExpression):
        narrowed = success_type(checker.infer(expression.value))
        fallback = checker.infer(expression.fallback)
        return checker.record(expression, union_type(narrowed, fallback))

    if isinstance(expression, OrBlockExpression):
        narrowed = success_type(checker.infer(expression.value))
        checker.check_block(expression.handler)
        handler_type = checked_block_normal_type(checker, expression.handler)
        result_type = (
            narrowed
            if handler_type is None
            else union_type(narrowed, handler_type)
        )
        return checker.record(expression, result_type)

    if isinstance(expression, MatchExpression):
        value_type = checker.infer(expression.value)
        results = []
        for arm in expression.arms:
            checker.scopes.append({})
            try:
                if arm.binding is not None:
                    checker.declare(
                        arm.binding,
                        checker.variant_payload(value_type, arm.variant),
                        arm.location,
                        "match-payload",
                    )
                results.append(checker.infer(arm.body))
            finally:
                checker.scopes.pop()
        return checker.record(expression, union_type(*results))

    if isinstance(expression, AssignmentExpression):
        value = checker.infer(expression.value)
        checker.infer(expression.target)
        return checker.record(expression, value)

    raise AssertionError(type(expression).__name__)