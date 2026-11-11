from __future__ import annotations

from pathlib import Path
import unittest

from koschei.ast_nodes import BinaryExpression, LetStatement, ReturnStatement
from koschei.modules import Module, ModuleGraph, check_graph
from koschei.native_kernel_originality_v1 import audit_native_kernel_surface_v1
from koschei.native_kernel_v1 import (
    check_native_kernel,
    dependency_order,
    evaluate_native_kernel,
    lower_native_kernel,
    parse_native_kernel,
)


class NativeKernelV1Tests(unittest.TestCase):
    def test_closed_witness_graph_evaluates_and_passes_existing_type_checker(self) -> None:
        source = (
            "witness base 40\n"
            "witness fee 2\n"
            "witness total sum base fee\n"
            "witness doubled product total 2\n"
            "resolve doubled\n"
        )
        checked = check_native_kernel(source)
        self.assertEqual(checked.value, 84)
        self.assertEqual(
            checked.dependency_order,
            ("base", "fee", "total", "doubled"),
        )
        self.assertEqual(checked.semantic.functions, 1)
        self.assertEqual(checked.semantic.variables, 4)

    def test_native_lowering_satisfies_full_current_module_graph_backend_abi(self) -> None:
        checked = check_native_kernel(
            "witness base 40\n"
            "witness fee 2\n"
            "witness total sum base fee\n"
            "resolve total\n"
        )
        module = Module(
            name="<native-kernel-test>",
            path=Path("<native-kernel-test>"),
            program=checked.lowered,
            imports={},
        )
        graph = ModuleGraph(root="native", modules={"native": module})
        report = check_graph(graph)
        self.assertEqual(report.functions, 1)
        self.assertEqual(report.variables, 3)
        self.assertIsNotNone(graph.mir)
        self.assertIn("native", graph.mir.modules)

    def test_source_clause_order_is_not_execution_order(self) -> None:
        first = parse_native_kernel(
            "witness base 40\n"
            "witness fee 2\n"
            "witness total sum base fee\n"
            "resolve total\n"
        )
        shuffled = parse_native_kernel(
            "witness total sum base fee\n"
            "witness fee 2\n"
            "resolve total\n"
            "witness base 40\n"
        )
        self.assertEqual(dependency_order(first), dependency_order(shuffled))
        self.assertEqual(evaluate_native_kernel(first), 42)
        self.assertEqual(evaluate_native_kernel(shuffled), 42)

    def test_forward_reference_is_native_and_lowers_by_dependency_not_line(self) -> None:
        kernel = parse_native_kernel(
            "witness total sum base fee\n"
            "witness base 40\n"
            "witness fee 2\n"
            "resolve total\n"
        )
        program = lower_native_kernel(kernel)
        statements = program.declarations[0].body.statements
        self.assertEqual(
            [item.name for item in statements if isinstance(item, LetStatement)],
            ["base", "fee", "total"],
        )
        self.assertIsInstance(statements[-1], ReturnStatement)
        total = statements[-2]
        self.assertIsInstance(total, LetStatement)
        self.assertIsInstance(total.value, BinaryExpression)
        self.assertEqual(total.value.operator, "+")

    def test_native_source_contains_no_legacy_function_or_block_surface(self) -> None:
        source = (
            "witness left 7\n"
            "witness right 5\n"
            "witness answer difference left right\n"
            "resolve answer\n"
        )
        forbidden_words = {
            "fn", "let", "return", "if", "else", "while", "for", "import",
            "struct", "enum", "match", "pure", "stateful",
        }
        words = set(source.replace("\n", " ").split())
        self.assertTrue(words.isdisjoint(forbidden_words))
        for symbol in "(){}[],:.=+-*/%;!<>":
            self.assertNotIn(symbol, source)
        self.assertEqual(check_native_kernel(source).value, 2)

    def test_native_surface_passes_originality_contract_with_explicit_provenance(self) -> None:
        self.assertEqual(audit_native_kernel_surface_v1(), ())


if __name__ == "__main__":
    unittest.main()