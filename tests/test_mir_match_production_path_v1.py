from __future__ import annotations

from koschei.ast_nodes import (
    Block,
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
from koschei.mir_ir import MirAstFallback
from koschei.type_system import INT, generic
from koschei.typed_hir import TypedHIRChecker, TypedHIRReport


def _checked_match_function():
    loc = SourceLocation(1, 1)
    checker = TypedHIRChecker(Program(()))
    checker.scopes.append({"choice": generic("Option", INT)})

    expression = MatchExpression(
        Identifier("choice", loc),
        (
            MatchArm("Some", "payload", Identifier("payload", loc), loc),
            MatchArm("None", None, Literal(0, loc), loc),
        ),
        loc,
    )
    checker.infer(expression)
    report = TypedHIRReport(
        tuple(checker.bindings),
        tuple(checker.expressions),
        checker.collections,
        tuple(checker.match_resolutions),
    )
    declaration = FunctionDeclaration(
        "unwrap_or_zero",
        (Parameter("choice", TypeRef(("Option<Int>",), loc), loc),),
        TypeRef(("Int",), loc),
        Block((ReturnStatement(expression, loc),)),
        loc,
    )
    return declaration, report


def test_production_match_lowering_never_emits_match_ast_fallback() -> None:
    declaration, report = _checked_match_function()

    blocks = lower_function_blocks_v1(declaration, report)
    instructions = tuple(
        instruction
        for block in blocks
        for instruction in block.instructions
    )

    assert any(isinstance(item, MirVariantIs) for item in instructions)
    assert any(isinstance(item, MirVariantPayload) for item in instructions)
    assert not any(
        isinstance(item, MirAstFallback) and item.node_kind == "MatchExpression"
        for item in instructions
    )
