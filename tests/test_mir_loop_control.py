from types import SimpleNamespace

import pytest

from koschei.ast_nodes import (
    Block,
    BreakStatement,
    ContinueStatement,
    FunctionDeclaration,
    Literal,
    SourceLocation,
    WhileStatement,
)
from koschei.mir_ir import MirAstFallback, MirJump, lower_function_blocks

LOCATION = SourceLocation(1, 1)
TYPED_REPORT = SimpleNamespace(expressions=[])


def lower_loop(statement):
    declaration = FunctionDeclaration(
        name="main",
        parameters=(),
        return_type=None,
        body=Block((statement,)),
        location=LOCATION,
    )
    return lower_function_blocks(declaration, TYPED_REPORT)


def test_break_lowers_to_exit_jump_without_ast_fallback() -> None:
    blocks = lower_loop(
        WhileStatement(
            condition=Literal(True, LOCATION),
            body=Block((BreakStatement(LOCATION),)),
            location=LOCATION,
        )
    )
    assert not any(
        isinstance(instruction, MirAstFallback)
        for block in blocks
        for instruction in block.instructions
    )
    body = blocks[2]
    assert isinstance(body.terminator, MirJump)
    assert body.terminator.target == 3


def test_continue_lowers_to_condition_jump_without_ast_fallback() -> None:
    blocks = lower_loop(
        WhileStatement(
            condition=Literal(True, LOCATION),
            body=Block((ContinueStatement(LOCATION),)),
            location=LOCATION,
        )
    )
    assert not any(
        isinstance(instruction, MirAstFallback)
        for block in blocks
        for instruction in block.instructions
    )
    body = blocks[2]
    assert isinstance(body.terminator, MirJump)
    assert body.terminator.target == 1


def test_loop_control_outside_loop_fails_closed() -> None:
    for statement in (BreakStatement(LOCATION), ContinueStatement(LOCATION)):
        declaration = FunctionDeclaration(
            name="main",
            parameters=(),
            return_type=None,
            body=Block((statement,)),
            location=LOCATION,
        )
        with pytest.raises(ValueError, match="outside a loop"):
            lower_function_blocks(declaration, TYPED_REPORT)
