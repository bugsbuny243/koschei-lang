from types import SimpleNamespace

from koschei.ast_nodes import (
    Block,
    ExpressionStatement,
    ForStatement,
    FunctionDeclaration,
    Literal,
    OrBlockExpression,
    ReturnStatement,
    SourceLocation,
    TypeRef,
)
from koschei.mir_extension_instructions_v4 import MirIsRuntimeError, MirUnit
from koschei.mir_ir import MirAstFallback, MirConst, MirIterInit, MirReturn, MirStore
from koschei.mir_or_return_normalization_v1 import lower_function_blocks_v1
from koschei.type_system import ERROR, GenericType, INT, VOID, union_type


def _loc(column: int = 1) -> SourceLocation:
    return SourceLocation(1, column)


def _typed_report(*pairs):
    return SimpleNamespace(
        expressions=tuple(
            SimpleNamespace(expression=expression, type=type_node)
            for expression, type_node in pairs
        )
    )


def _lower(handler: Block, *handler_pairs, expression_type):
    location = _loc()
    fallible = Literal("fallible-sentinel", _loc(2))
    expression = OrBlockExpression(fallible, handler, location)
    declaration = FunctionDeclaration(
        "main",
        (),
        TypeRef(("Int",), location),
        Block((ReturnStatement(expression, location),)),
        location,
    )
    report = _typed_report(
        (fallible, GenericType("Option", (INT,))),
        *handler_pairs,
        (expression, expression_type),
    )
    return lower_function_blocks_v1(declaration, report)


def test_or_block_for_tail_is_explicit_value_cfg_without_ast_fallback():
    iterable = Literal([1, 2], _loc(8))
    body_value = Literal(7, _loc(12))
    loop = ForStatement(
        "item",
        iterable,
        Block((ExpressionStatement(body_value, body_value.location),)),
        _loc(8),
    )
    blocks = _lower(
        Block((loop,)),
        (iterable, GenericType("List", (INT,))),
        (body_value, INT),
        expression_type=union_type(INT, VOID),
    )
    instructions = [item for block in blocks for item in block.instructions]

    assert not any(isinstance(item, MirAstFallback) for item in instructions)
    assert any(isinstance(item, MirUnit) for item in instructions)
    assert any(isinstance(item, MirIterInit) for item in instructions)
    assert any(isinstance(item, MirIsRuntimeError) for item in instructions)
    assert any(isinstance(item, MirStore) for item in instructions)


def test_or_block_for_iterable_error_is_loop_value_not_function_return():
    iterable = Literal("iterable-error", _loc(8))
    body_value = Literal(7, _loc(12))
    loop = ForStatement(
        "item",
        iterable,
        Block((ExpressionStatement(body_value, body_value.location),)),
        _loc(8),
    )
    blocks = _lower(
        Block((loop,)),
        (iterable, union_type(GenericType("List", (INT,)), ERROR)),
        (body_value, INT),
        expression_type=union_type(INT, ERROR, VOID),
    )
    instructions = [item for block in blocks for item in block.instructions]
    iterable_const = next(
        item
        for item in instructions
        if isinstance(item, MirConst) and item.value == "iterable-error"
    )

    assert not any(isinstance(item, MirAstFallback) for item in instructions)
    assert any(
        isinstance(item, MirStore) and item.source == iterable_const.target
        for item in instructions
    )
    assert not any(
        isinstance(block.terminator, MirReturn)
        and block.terminator.value == iterable_const.target
        for block in blocks
    )
