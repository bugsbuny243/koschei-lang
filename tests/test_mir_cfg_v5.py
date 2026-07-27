from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from koschei.ast_nodes import SourceLocation
from koschei.mir import MirIntegrityError, require_mir, to_dict
from koschei.mir_ir import (
    MirAstFallback,
    MirBasicBlock,
    MirBranch,
    MirConst,
    MirJump,
    MirLoad,
    MirReturn,
    MirStore,
    instruction_kind,
    validate_blocks,
)
from koschei.modules import check_graph, load_graph
from koschei.type_system import NamedType, render_type


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "examples"


class MirCfgTestCase(unittest.TestCase):
    def checked_mir(self, source: str, *, name: str = "main.ks"):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / name
        path.write_text(source.strip() + "\n", encoding="utf-8")
        graph = load_graph(path)
        check_graph(graph)
        return require_mir(graph)

    def main_function(self, source: str):
        mir = self.checked_mir(source)
        return mir, mir.root_module.functions[0]


class MirStraightLineCfgTests(MirCfgTestCase):
    def test_straight_line_program_has_one_terminated_block(self) -> None:
        graph = load_graph(EXAMPLES / "hello.ks")
        check_graph(graph)
        function = require_mir(graph).root_module.functions[0]

        self.assertEqual(len(function.blocks), 1)
        self.assertIsInstance(function.blocks[0].terminator, MirReturn)
        kinds = [instruction_kind(item) for item in function.blocks[0].instructions]
        self.assertIn("const", kinds)
        self.assertIn("bind", kinds)
        self.assertIn("load", kinds)
        self.assertIn("call", kinds)
        self.assertNotIn("astfallback", kinds)

    def test_identifier_assignment_becomes_store(self) -> None:
        _, function = self.main_function(
            """
            fn main() {
                let mut value = 1
                value = value + 1
                println(value)
            }
            """
        )

        stores = [
            instruction
            for block in function.blocks
            for instruction in block.instructions
            if isinstance(instruction, MirStore)
        ]
        self.assertEqual(len(stores), 1)
        self.assertEqual(stores[0].name, "value")
        self.assertEqual(render_type(stores[0].type), "Int")

    def test_core_normalized_instructions_keep_structural_types(self) -> None:
        _, function = self.main_function(
            """
            fn main() {
                let mut value = 1
                value = -value + 2
                if value > 0 {
                    println(value)
                }
            }
            """
        )

        for block in function.blocks:
            for instruction in block.instructions:
                rendered = render_type(instruction.type)
                if instruction_kind(instruction) == "load" and getattr(
                    instruction, "name", ""
                ) == "println":
                    self.assertEqual(rendered, "_")
                else:
                    self.assertNotEqual(
                        rendered,
                        "_",
                        f"{instruction_kind(instruction)} lost its structural type",
                    )


class MirControlFlowCfgTests(MirCfgTestCase):
    def test_if_else_lowers_to_branch_then_else_and_join(self) -> None:
        _, function = self.main_function(
            """
            fn main() {
                let flag = true
                if flag {
                    println("yes")
                } else {
                    println("no")
                }
            }
            """
        )

        self.assertEqual([block.id for block in function.blocks], [0, 1, 2, 3])
        entry = function.blocks[0]
        self.assertIsInstance(entry.terminator, MirBranch)
        self.assertEqual(
            (entry.terminator.then_block, entry.terminator.else_block), (1, 2)
        )
        self.assertEqual(function.blocks[1].terminator, MirJump(3))
        self.assertEqual(function.blocks[2].terminator, MirJump(3))
        self.assertIsInstance(function.blocks[3].terminator, MirReturn)

    def test_while_has_condition_branch_and_back_edge(self) -> None:
        _, function = self.main_function(
            """
            fn main() {
                let mut i = 0
                while i < 3 {
                    i = i + 1
                }
                println(i)
            }
            """
        )

        self.assertEqual(function.blocks[0].terminator, MirJump(1))
        self.assertIsInstance(function.blocks[1].terminator, MirBranch)
        branch = function.blocks[1].terminator
        self.assertEqual((branch.then_block, branch.else_block), (2, 3))
        self.assertEqual(function.blocks[2].terminator, MirJump(1))
        self.assertIsInstance(function.blocks[3].terminator, MirReturn)
        self.assertTrue(
            any(
                isinstance(instruction, MirStore)
                for instruction in function.blocks[2].instructions
            )
        )

    def test_every_dependency_function_has_valid_blocks(self) -> None:
        graph = load_graph(EXAMPLES / "app.ks")
        check_graph(graph)
        mir = require_mir(graph)

        self.assertGreater(len(mir.modules), 1)
        for module in mir.in_dependency_order():
            for function in module.functions:
                self.assertTrue(function.blocks, f"{module.name}.{function.name}")
                validate_blocks(function.blocks)


class MirFallbackBoundaryTests(MirCfgTestCase):
    def test_for_loop_is_explicit_statement_fallback(self) -> None:
        _, function = self.main_function(
            """
            fn main() {
                for value in [1, 2, 3] {
                    println(value)
                }
            }
            """
        )

        fallbacks = [
            instruction
            for block in function.blocks
            for instruction in block.instructions
            if isinstance(instruction, MirAstFallback)
        ]
        self.assertEqual([item.node_kind for item in fallbacks], ["ForStatement"])
        self.assertIsNone(fallbacks[0].target)

    def test_aggregate_and_match_fallbacks_are_visible_not_erased(self) -> None:
        _, function = self.main_function(
            """
            enum Maybe<T> {
                Present(T),
                Missing,
            }

            fn main() {
                let item = Present("Ada")
                let text = match item {
                    Present(value) => value,
                    Missing => "none",
                }
                println(text)
            }
            """
        )

        node_kinds = {
            instruction.node_kind
            for block in function.blocks
            for instruction in block.instructions
            if isinstance(instruction, MirAstFallback)
        }
        self.assertIn("MatchExpression", node_kinds)

    def test_json_reports_block_instruction_and_fallback_metrics(self) -> None:
        mir = self.checked_mir(
            """
            fn main() {
                for value in [1, 2] {
                    println(value)
                }
            }
            """
        )
        function = to_dict(mir)["modules"][0]["functions"][0]

        self.assertEqual(function["basic_blocks"], 1)
        self.assertGreaterEqual(function["instructions"], 1)
        self.assertEqual(function["ast_fallbacks"], 1)
        self.assertEqual(function["blocks"][0]["terminator"]["kind"], "return")


class MirCfgIntegrityTests(MirCfgTestCase):
    def test_unknown_jump_target_is_rejected(self) -> None:
        blocks = (MirBasicBlock(0, (), MirJump(99)),)

        with self.assertRaisesRegex(ValueError, "unknown block 99"):
            validate_blocks(blocks)

    def test_duplicate_temp_definition_is_rejected(self) -> None:
        location = SourceLocation(1, 1)
        blocks = (
            MirBasicBlock(
                0,
                (
                    MirConst(0, 1, NamedType("Int"), location),
                    MirConst(0, 2, NamedType("Int"), location),
                ),
                MirReturn(0),
            ),
        )

        with self.assertRaisesRegex(ValueError, "defined more than once"):
            validate_blocks(blocks)

    def test_undefined_temp_use_is_rejected(self) -> None:
        blocks = (MirBasicBlock(0, (), MirReturn(7)),)

        with self.assertRaisesRegex(ValueError, "undefined values"):
            validate_blocks(blocks)

    def test_instruction_mutation_breaks_graph_seal(self) -> None:
        mir = self.checked_mir('fn main() { println(41) }')
        module = mir.root_module
        function = module.functions[0]
        first_block = function.blocks[0]
        first_instruction = first_block.instructions[0]
        self.assertIsInstance(first_instruction, MirLoad)
        const_instruction = next(
            item for item in first_block.instructions if isinstance(item, MirConst)
        )
        changed_const = replace(const_instruction, value=42)
        changed_instructions = tuple(
            changed_const if item is const_instruction else item
            for item in first_block.instructions
        )
        changed_block = replace(first_block, instructions=changed_instructions)
        changed_function = replace(function, blocks=(changed_block,))
        changed_module = replace(module, functions=(changed_function,))
        changed_modules = dict(mir.modules)
        changed_modules[mir.root] = changed_module
        forged = replace(mir, modules=changed_modules)

        with self.assertRaises(MirIntegrityError) as caught:
            forged.assert_sealed()

        self.assertEqual(caught.exception.code, "KS5002")


if __name__ == "__main__":
    unittest.main()
