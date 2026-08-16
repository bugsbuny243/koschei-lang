from __future__ import annotations

import unittest

from koschei.native_ir_v1 import execute_native_ir_v1, lower_value_graph_to_native_ir_v1
from koschei.native_value_domains_v1 import GLYPHS, TRUTH, WHOLE, parse_native_value_graph


class NativeIrV1Tests(unittest.TestCase):
    def test_whole_executes_without_legacy_ast(self):
        graph = parse_native_value_graph(
            "witness base 40\n"
            "witness fee 2\n"
            "witness total sum base fee\n"
            "resolve total\n"
        )
        ir = lower_value_graph_to_native_ir_v1(graph)
        value = execute_native_ir_v1(ir)
        self.assertEqual((value.domain, value.value), (WHOLE, 42))
        self.assertNotIn("Program", type(ir).__name__)

    def test_truth_and_same_execute_natively(self):
        graph = parse_native_value_graph(
            "witness left truth yes\n"
            "witness right truth yes\n"
            "witness result same left right\n"
            "resolve result\n"
        )
        value = execute_native_ir_v1(lower_value_graph_to_native_ir_v1(graph))
        self.assertEqual((value.domain, value.value), (TRUTH, True))

    def test_glyph_merge_executes_natively(self):
        graph = parse_native_value_graph(
            "witness left glyphs 3 kos\n"
            "witness right glyphs 5 chei!\n"
            "witness result merge left right\n"
            "resolve result\n"
        )
        value = execute_native_ir_v1(lower_value_graph_to_native_ir_v1(graph))
        self.assertEqual((value.domain, value.value), (GLYPHS, "koschei!"))

    def test_source_clause_order_remains_nonsemantic(self):
        graph = parse_native_value_graph(
            "witness total sum base fee\n"
            "witness fee 2\n"
            "witness base 40\n"
            "resolve total\n"
        )
        value = execute_native_ir_v1(lower_value_graph_to_native_ir_v1(graph))
        self.assertEqual(value.value, 42)

    def test_native_ir_contains_no_legacy_ast_nodes(self):
        graph = parse_native_value_graph("witness x 1\nresolve x\n")
        ir = lower_value_graph_to_native_ir_v1(graph)
        names = {type(ir).__name__}
        names.update(type(item).__name__ for item in ir.witnesses)
        self.assertTrue(names.isdisjoint({"Program", "GenericFunctionDeclaration", "LetStatement", "ReturnStatement", "BinaryExpression"}))


if __name__ == "__main__":
    unittest.main()
