import unittest
from types import SimpleNamespace

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


class MirLoopControlTests(unittest.TestCase):
    def test_break_lowers_to_exit_jump_without_ast_fallback(self) -> None:
        blocks = lower_loop(
            WhileStatement(
                condition=Literal(True, LOCATION),
                body=Block((BreakStatement(LOCATION),)),
                location=LOCATION,
            )
        )
        self.assertFalse(
            any(
                isinstance(instruction, MirAstFallback)
                for block in blocks
                for instruction in block.instructions
            )
        )
        body = blocks[2]
        self.assertIsInstance(body.terminator, MirJump)
        self.assertEqual(body.terminator.target, 3)

    def test_continue_lowers_to_condition_jump_without_ast_fallback(self) -> None:
        blocks = lower_loop(
            WhileStatement(
                condition=Literal(True, LOCATION),
                body=Block((ContinueStatement(LOCATION),)),
                location=LOCATION,
            )
        )
        self.assertFalse(
            any(
                isinstance(instruction, MirAstFallback)
                for block in blocks
                for instruction in block.instructions
            )
        )
        body = blocks[2]
        self.assertIsInstance(body.terminator, MirJump)
        self.assertEqual(body.terminator.target, 1)


if __name__ == "__main__":
    unittest.main()
