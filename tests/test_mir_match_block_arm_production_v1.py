from __future__ import annotations

from koschei.ast_nodes import (
    Block,
    ExpressionStatement,
    FunctionDeclaration,
    Identifier,
    Literal,
    MatchArm,
    MatchExpression,
    Parameter,
    Program,
    ReturnStatement,
    SourceLocation,
    TypeRef,
)
from koschei.mir_canonical_lowering_v1 import lower_function_blocks_v1
from koschei.mir_extension_instructions_v4 import MirVariantIs, MirVariantPayload
from koschei.mir_ir import MirAstFallback, MirReturn
from koschei.type_system import INT, generic
from koschei.typed_hir import TypedHIRChecker, TypedHIRReport


def _report_for(expression: MatchExpression, loc: SourceLocation) -> TypedHIRReport:
    checker = TypedHIRChecker(Program(()))
    checker.scopes.append({"choice": generic("Option", INT)})
    checker.infer(expression)
    return TypedHIRReport(
        tuple(checker.bindings),
        tuple(checker.expressions),
        checker.collections,
        tuple(checker.match_resolutions),
    )


def _declaration(expression: MatchExpression, loc: SourceLocation) -> FunctionDeclaration:
    return FunctionDeclaration(
        "unwrap_block",
        (Parameter("choice", TypeRef(("Option<Int>",), loc), loc),),
        TypeRef(("Int",), loc),
        Block((ReturnStatement(expression, loc),)),
        loc,
    )


def test_match_block_arms_lower_without_ast_fallback() -> None:
    loc = SourceLocation(1, 1)
    expression = MatchExpression(
        Identifier("choice", loc),
        (
            MatchArm(
                "Some",
                "payload",
                Block((ExpressionStatement(Identifier("payload", loc), loc),)),
                loc,
            ),
            MatchArm(
                "None",
                None,
                Block((ExpressionStatement(Literal(0, loc), loc),)),
                loc,
            ),
        ),
        loc,
    )

    blocks = lower_function_blocks_v1(
        _declaration(expression, loc),
        _report_for(expression, loc),
    )
    instructions = tuple(item for block in blocks for item in block.instructions)

    assert any(isinstance(item, MirVariantIs) for item in instructions)
    assert any(isinstance(item, MirVariantPayload) for item in instructions)
    assert not any(isinstance(item, MirAstFallback) for item in instructions)


def test_match_block_arm_may_terminate_its_own_path() -> None:
    loc = SourceLocation(1, 1)
    expression = MatchExpression(
        Identifier("choice", loc),
        (
            MatchArm(
                "Some",
                "payload",
                Block((ReturnStatement(Identifier("payload", loc), loc),)),
                loc,
            ),
            MatchArm(
                "None",
                None,
                Block((ExpressionStatement(Literal(0, loc), loc),)),
                loc,
            ),
        ),
        loc,
    )

    blocks = lower_function_blocks_v1(
        _declaration(expression, loc),
        _report_for(expression, loc),
    )

    assert any(isinstance(block.terminator, MirReturn) for block in blocks)
    assert not any(
        isinstance(item, MirAstFallback)
        for block in blocks
        for item in block.instructions
    )
