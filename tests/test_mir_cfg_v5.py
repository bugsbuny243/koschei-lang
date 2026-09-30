from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from koschei.ast_nodes import SourceLocation
from koschei.mir import MirIntegrityError, require_mir, to_dict
from koschei.mir_extension_instructions_v4 import MirVariantIs, MirVariantPayload
from koschei.mir_ir import (
    MirAstFallback,
    MirBasicBlock,
    MirBranch,
    MirConst,
    MirIterHasNext,
    MirIterInit,
    MirIterNext,
    MirJump,
    MirList,
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

        by_id = {block.id: block for block in function.blocks}
        entry = by_id[0]
        self.assertIsInstance(entry.terminator, MirBranch)

        # v4 first guards Error-valued conditions, then performs the Bool branch.
        error_block = by_id[entry.terminator.then_block]
        decision_block = by_id[entry.terminator.else_block]
        self.assertIsInstance(error_block.terminator, MirJump)
        self.assertIsInstance(decision_block.terminator, MirBranch)

        then_block = by_id[decision_block.terminator.then_block]
        else_block = by_id[decision_block.terminator.else_block]
        self.assertIsInstance(then_block.terminator, MirJump)
        self.assertIsInstance(else_block.terminator, MirJump)
        join = then_block.terminator.target
        self.assertEqual(else_block.terminator.target, join)
        self.assertEqual(error_block.terminator.target, join)
        self.assertIsInstance(by_id[join].terminator, MirReturn)

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

        by_id = {block.id: block for block in function.blocks}
        self.assertIsInstance(by_id[0].terminator, MirJump)
        condition_id = by_id[0].terminator.target
        condition = by_id[condition_id]
        self.assertIsInstance(condition.terminator, MirBranch)

        # One edge handles condition Error; the other reaches the Bool decision.
        decision = by_id[condition.terminator.else_block]
        self.assertIsInstance(decision.terminator, MirBranch)
        exit_id = decision.terminator.else_block
        self.assertIsInstance(by_id[exit_id].terminator, MirReturn)

        # Body completion may pass through an Error guard, but a successful
        # iteration must have one explicit back-edge to the condition block.
        self.assertTrue(
            any(
                isinstance(block.terminator, MirJump)
                and block.terminator.target == condition_id
                for block in function.blocks
            )
        )
        self.assertTrue(
            any(
                isinstance(instruction, MirStore)
                for block in function.blocks
                for instruction in block.instructions
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
    def test_list_for_loop_is_normalized_into_iterator_cfg(self) -> None:
        _, function = self.main_function(
            """
            fn main() {
                for value in [1, 2, 3] {
                    println(value)
                }
            }
            """
        )

        instructions = [
            instruction
            for block in function.blocks
            for instruction in block.instructions
        ]
        self.assertFalse(any(isinstance(item, MirAstFallback) for item in instructions))
        self.assertTrue(any(isinstance(item, MirList) for item in instructions))
        self.assertTrue(any(isinstance(item, MirIterInit) for item in instructions))
        self.assertTrue(any(isinstance(item, MirIterHasNext) for item in instructions))
        self.assertTrue(any(isinstance(item, MirIterNext) for item in instructions))
        by_id = {block.id: block for block in function.blocks}
        entry = by_id[0]
        self.assertIsInstance(entry.terminator, MirBranch)

        iterator_init = next(
            block
            for block in function.blocks
            if any(isinstance(item, MirIterInit) for item in block.instructions)
        )
        self.assertIsInstance(iterator_init.terminator, MirJump)
        condition_id = iterator_init.terminator.target
        self.assertIsInstance(by_id[condition_id].terminator, MirBranch)

        self.assertTrue(
            any(
                isinstance(block.terminator, MirJump)
                and block.terminator.target == condition_id
                for block in function.blocks
            )
        )
        self.assertTrue(
            any(isinstance(block.terminator, MirReturn) for block in function.blocks)
        )

    def test_aggregate_and_match_are_normalized_without_ast_fallback(self) -> None:
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

        instructions = [
            instruction
            for block in function.blocks
            for instruction in block.instructions
        ]
        self.assertTrue(any(isinstance(item, MirVariantIs) for item in instructions))
        self.assertTrue(any(isinstance(item, MirVariantPayload) for item in instructions))
        self.assertFalse(any(isinstance(item, MirAstFallback) for item in instructions))

    def test_json_reports_normalized_for_cfg_without_fallbacks(self) -> None:
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

        self.assertGreaterEqual(function["basic_blocks"], 6)
        self.assertGreaterEqual(function["instructions"], 8)
        self.assertEqual(function["ast_fallbacks"], 0)
        terminators = [block["terminator"]["kind"] for block in function["blocks"]]
        self.assertIn("branch", terminators)
        self.assertIn("jump", terminators)
        self.assertIn("return", terminators)


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
