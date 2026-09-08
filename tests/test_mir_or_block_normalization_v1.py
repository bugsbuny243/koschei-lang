from types import SimpleNamespace

from koschei.ast_nodes import (
    Block,
    ExpressionStatement,
    FunctionDeclaration,
    IfStatement,
    Literal,
    OrBlockExpression,
    ReturnStatement,
    SourceLocation,
    TypeRef,
    WhileStatement,
)
from koschei.mir_extension_instructions_v4 import (
    MirFallibleIsSuccess,
    MirFalliblePayload,
    MirIsRuntimeError,
    MirUnit,
)
from koschei.mir_ir import MirAstFallback, MirBind, MirBranch, MirConst, MirReturn
from koschei.mir_or_return_normalization_v1 import lower_function_blocks_v1
from koschei.type_system import BOOL, ERROR, GenericType, INT, union_type


def _loc(column: int = 1) -> SourceLocation:
    return SourceLocation(1, column)


def _typed_report(*pairs):
    return SimpleNamespace(
        expressions=tuple(
            SimpleNamespace(expression=expression, type=type_node)
            for expression, type_node in pairs
        )
    )


def _lower(handler: Block, *handler_pairs, expression_type=INT):
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


def test_or_block_normalizes_last_handler_value_on_failure_only():
    first = Literal(3, _loc(10))
    last = Literal(7, _loc(14))
    handler = Block(
        (
            ExpressionStatement(first, first.location),
            ExpressionStatement(last, last.location),
        )
    )
    blocks = _lower(handler, (first, INT), (last, INT))
    instructions = [item for block in blocks for item in block.instructions]

    assert not any(isinstance(item, MirAstFallback) for item in instructions)
    assert sum(isinstance(item, MirFallibleIsSuccess) for item in instructions) == 1
    assert sum(isinstance(item, MirFalliblePayload) for item in instructions) == 1

    entry = blocks[0]
    assert isinstance(entry.terminator, MirBranch)
    success = next(block for block in blocks if block.id == entry.terminator.then_block)
    failure = next(block for block in blocks if block.id == entry.terminator.else_block)

    assert not any(isinstance(item, MirConst) and item.value in {3, 7} for item in success.instructions)
    assert any(isinstance(item, MirConst) and item.value == 3 for item in failure.instructions)
    assert any(isinstance(item, MirConst) and item.value == 7 for item in failure.instructions)
    success_bind = next(item for item in success.instructions if isinstance(item, MirBind))
    failure_bind = next(item for item in failure.instructions if isinstance(item, MirBind))
    assert success_bind.name == failure_bind.name


def test_or_block_handler_return_is_function_terminator_and_skips_unreachable_tail():
    returned = Literal(11, _loc(10))
    unreachable = Literal(99, _loc(20))
    handler = Block(
        (
            ReturnStatement(returned, returned.location),
            ExpressionStatement(unreachable, unreachable.location),
        )
    )
    blocks = _lower(handler, (returned, INT), (unreachable, INT))
    instructions = [item for block in blocks for item in block.instructions]

    assert not any(isinstance(item, MirAstFallback) for item in instructions)
    assert any(isinstance(item, MirConst) and item.value == 11 for item in instructions)
    assert not any(isinstance(item, MirConst) and item.value == 99 for item in instructions)
    assert any(isinstance(block.terminator, MirReturn) and block.terminator.value is not None for block in blocks)


def test_or_block_empty_handler_uses_canonical_unit_not_host_sentinel():
    blocks = _lower(Block())
    instructions = [item for block in blocks for item in block.instructions]

    assert not any(isinstance(item, MirAstFallback) for item in instructions)
    assert sum(isinstance(item, MirUnit) for item in instructions) == 1


def test_or_block_if_tail_is_explicit_value_cfg_without_ast_fallback():
    condition = Literal(True, _loc(8))
    then_value = Literal(7, _loc(12))
    else_value = Literal(9, _loc(18))
    tail_if = IfStatement(
        condition,
        Block((ExpressionStatement(then_value, then_value.location),)),
        Block((ExpressionStatement(else_value, else_value.location),)),
        _loc(8),
    )
    blocks = _lower(
        Block((tail_if,)),
        (condition, BOOL),
        (then_value, INT),
        (else_value, INT),
    )
    instructions = [item for block in blocks for item in block.instructions]

    assert not any(isinstance(item, MirAstFallback) for item in instructions)
    assert any(isinstance(item, MirIsRuntimeError) for item in instructions)
    assert sum(isinstance(block.terminator, MirBranch) for block in blocks) >= 3
    assert any(isinstance(item, MirConst) and item.value == 7 for item in instructions)
    assert any(isinstance(item, MirConst) and item.value == 9 for item in instructions)


def test_or_block_if_error_condition_has_explicit_error_result_path():
    condition = Literal("error-sentinel", _loc(8))
    then_value = Literal(7, _loc(12))
    else_value = Literal(9, _loc(18))
    tail_if = IfStatement(
        condition,
        Block((ExpressionStatement(then_value, then_value.location),)),
        Block((ExpressionStatement(else_value, else_value.location),)),
        _loc(8),
    )
    blocks = _lower(
        Block((tail_if,)),
        (condition, union_type(BOOL, ERROR)),
        (then_value, INT),
        (else_value, INT),
        expression_type=union_type(INT, ERROR),
    )
    instructions = [item for block in blocks for item in block.instructions]

    assert not any(isinstance(item, MirAstFallback) for item in instructions)
    assert any(isinstance(item, MirIsRuntimeError) for item in instructions)
    error_result_binds = [
        item
        for block in blocks
        for item in block.instructions
        if isinstance(item, MirBind) and item.source == 2
    ]
    assert error_result_binds or sum(isinstance(item, MirBind) for item in instructions) >= 4


def test_or_block_loop_tail_remains_explicit_migration_fallback():
    condition = Literal(False, _loc(8))
    body_value = Literal(7, _loc(12))
    handler = Block(
        (
            WhileStatement(
                condition,
                Block((ExpressionStatement(body_value, body_value.location),)),
                _loc(8),
            ),
        )
    )
    blocks = _lower(handler, (condition, BOOL), (body_value, INT))
    instructions = [item for block in blocks for item in block.instructions]

    fallbacks = [item for item in instructions if isinstance(item, MirAstFallback)]
    assert len(fallbacks) == 1
    assert fallbacks[0].node_kind == "OrBlockExpression"
    assert not any(isinstance(item, MirConst) and item.value == 7 for item in instructions)
