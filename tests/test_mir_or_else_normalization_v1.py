from types import SimpleNamespace

from koschei.ast_nodes import (
    Block,
    FunctionDeclaration,
    Literal,
    OrElseExpression,
    ReturnStatement,
    SourceLocation,
    TypeRef,
)
from koschei.mir_extension_instructions_v4 import (
    MirFallibleIsSuccess,
    MirFalliblePayload,
)
from koschei.mir_ir import (
    MirAstFallback,
    MirBind,
    MirBranch,
    MirConst,
    MirJump,
    MirLoad,
)
from koschei.mir_or_return_normalization_v1 import lower_function_blocks_v1
from koschei.type_system import GenericType, INT


def _typed_report(*pairs):
    return SimpleNamespace(
        expressions=tuple(
            SimpleNamespace(expression=expression, type=type_node)
            for expression, type_node in pairs
        )
    )


def test_or_else_is_explicit_cfg_and_fallback_is_failure_only():
    location = SourceLocation(1, 1)
    fallible = Literal("fallible-sentinel", location)
    fallback = Literal(99, SourceLocation(1, 20))
    expression = OrElseExpression(fallible, fallback, location)
    declaration = FunctionDeclaration(
        "main",
        (),
        TypeRef(("Int",), location),
        Block((ReturnStatement(expression, location),)),
        location,
    )
    report = _typed_report(
        (fallible, GenericType("Option", (INT,))),
        (fallback, INT),
        (expression, INT),
    )

    blocks = lower_function_blocks_v1(declaration, report)
    instructions = [item for block in blocks for item in block.instructions]

    assert not any(isinstance(item, MirAstFallback) for item in instructions)
    assert sum(isinstance(item, MirFallibleIsSuccess) for item in instructions) == 1
    assert sum(isinstance(item, MirFalliblePayload) for item in instructions) == 1
    assert sum(isinstance(item, MirLoad) for item in instructions) == 1

    entry = blocks[0]
    assert isinstance(entry.terminator, MirBranch)
    success_id = entry.terminator.then_block
    failure_id = entry.terminator.else_block
    success = next(block for block in blocks if block.id == success_id)
    failure = next(block for block in blocks if block.id == failure_id)

    assert any(isinstance(item, MirFalliblePayload) for item in success.instructions)
    assert not any(
        isinstance(item, MirConst) and item.value == 99
        for item in success.instructions
    )
    assert any(
        isinstance(item, MirConst) and item.value == 99
        for item in failure.instructions
    )
    assert not any(isinstance(item, MirFalliblePayload) for item in failure.instructions)

    success_bind = next(item for item in success.instructions if isinstance(item, MirBind))
    failure_bind = next(item for item in failure.instructions if isinstance(item, MirBind))
    assert success_bind.name == failure_bind.name
    assert isinstance(success.terminator, MirJump)
    assert isinstance(failure.terminator, MirJump)
    assert success.terminator.target == failure.terminator.target
