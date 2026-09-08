from koschei.ast_nodes import (
    Block,
    ExpressionStatement,
    FunctionDeclaration,
    Identifier,
    IfStatement,
    Literal,
    OrBlockExpression,
    Parameter,
    Program,
    ReturnStatement,
    SourceLocation,
    TypeRef,
)
from koschei.typed_hir import lower_typed_hir
from koschei.type_system import render_type


def _loc(column: int = 1) -> SourceLocation:
    return SourceLocation(1, column)


def _expression_type(report, expression) -> str:
    match = next(item for item in report.expressions if item.expression is expression)
    return render_type(match.type)


def _program_with_handler(handler: Block, return_types=("Int", "String")):
    location = _loc()
    fallible = Identifier("value", _loc(2))
    expression = OrBlockExpression(fallible, handler, location)
    function = FunctionDeclaration(
        "choose",
        (Parameter("value", TypeRef(("Option<Int>",), location), location),),
        TypeRef(tuple(return_types), location),
        Block((ReturnStatement(expression, location),)),
        location,
    )
    return Program((function,)), expression


def test_or_block_type_includes_handler_normal_exit_value():
    handler = Block((ExpressionStatement(Literal("fallback", _loc(10)), _loc(10)),))
    program, expression = _program_with_handler(handler)

    report = lower_typed_hir(program)

    assert _expression_type(report, expression) == "Int or String"


def test_or_block_early_function_return_does_not_pollute_expression_type():
    handler = Block(
        (
            ReturnStatement(Literal(7, _loc(10)), _loc(10)),
            ExpressionStatement(Literal("unreachable", _loc(20)), _loc(20)),
        )
    )
    program, expression = _program_with_handler(handler, return_types=("Int",))

    report = lower_typed_hir(program)

    assert _expression_type(report, expression) == "Int"


def test_or_block_tail_if_unions_only_normal_branch_values():
    condition = Literal(True, _loc(8))
    tail_if = IfStatement(
        condition,
        Block((ExpressionStatement(Literal("fallback", _loc(12)), _loc(12)),)),
        Block((ExpressionStatement(Literal(9, _loc(18)), _loc(18)),)),
        _loc(8),
    )
    handler = Block((tail_if,))
    program, expression = _program_with_handler(handler)

    report = lower_typed_hir(program)

    assert _expression_type(report, expression) == "Int or String"


def test_or_block_value_if_includes_error_valued_condition_in_result_type():
    location = _loc()
    fallible = Identifier("value", _loc(2))
    condition = Identifier("condition", _loc(8))
    tail_if = IfStatement(
        condition,
        Block((ExpressionStatement(Literal("fallback", _loc(12)), _loc(12)),)),
        Block((ExpressionStatement(Literal(9, _loc(18)), _loc(18)),)),
        _loc(8),
    )
    expression = OrBlockExpression(fallible, Block((tail_if,)), location)
    function = FunctionDeclaration(
        "choose",
        (
            Parameter("value", TypeRef(("Option<Int>",), location), location),
            Parameter("condition", TypeRef(("Bool", "Error"), location), location),
        ),
        TypeRef(("Int", "String", "Error"), location),
        Block((ReturnStatement(expression, location),)),
        location,
    )

    report = lower_typed_hir(Program((function,)))

    assert _expression_type(report, expression) == "Error or Int or String"
