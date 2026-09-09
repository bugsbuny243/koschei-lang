from koschei.ast_nodes import (
    Block,
    CallExpression,
    ExpressionStatement,
    FunctionDeclaration,
    Identifier,
    Literal,
    OrBlockExpression,
    Program,
    ReturnStatement,
    SourceLocation,
    TypeRef,
)
from koschei.interpreter import Interpreter


def _loc(column: int = 1) -> SourceLocation:
    return SourceLocation(1, column)


def _run_main(expression) -> object:
    location = _loc()
    main = FunctionDeclaration(
        "main",
        (),
        TypeRef(("Int",), location),
        Block((ReturnStatement(expression, location),)),
        location,
    )
    return Interpreter(Program((main,))).execute_main()


def test_or_block_uses_last_handler_statement_value_on_failure():
    fallible = CallExpression(Identifier("None", _loc(2)), (), _loc(2))
    handler = Block(
        (
            ExpressionStatement(Literal(3, _loc(10)), _loc(10)),
            ExpressionStatement(Literal(7, _loc(14)), _loc(14)),
        )
    )
    expression = OrBlockExpression(fallible, handler, _loc())

    assert _run_main(expression) == 7


def test_or_block_handler_return_remains_function_return():
    fallible = CallExpression(Identifier("None", _loc(2)), (), _loc(2))
    handler = Block(
        (
            ReturnStatement(Literal(11, _loc(10)), _loc(10)),
            ExpressionStatement(Literal(99, _loc(14)), _loc(14)),
        )
    )
    expression = OrBlockExpression(fallible, handler, _loc())

    assert _run_main(expression) == 11


def test_or_block_handler_is_skipped_on_success():
    fallible = CallExpression(
        Identifier("Some", _loc(2)),
        (Literal(5, _loc(7)),),
        _loc(2),
    )
    handler = Block((ReturnStatement(Literal(99, _loc(12)), _loc(12)),))
    expression = OrBlockExpression(fallible, handler, _loc())

    assert _run_main(expression) == 5
