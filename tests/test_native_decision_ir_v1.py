from __future__ import annotations

import unittest

from koschei.native_decision_ir_v1 import (
    execute_native_decision_ir_v1,
    lower_decision_graph_to_native_ir_v1,
)
from koschei.native_value_domains_v1 import GLYPHS, TRUTH, WHOLE


class NativeDecisionIrV1Tests(unittest.TestCase):
    def test_truth_selects_affirmative_without_legacy_ast(self):
        source = (
            "witness gate truth yes\n"
            "witness accepted glyphs 2 ok\n"
            "witness rejected glyphs 2 no\n"
            "witness result settle gate accepted rejected\n"
            "resolve result\n"
        )
        ir = lower_decision_graph_to_native_ir_v1(source)
        value = execute_native_decision_ir_v1(ir)
        self.assertEqual((value.domain, value.value), (GLYPHS, "ok"))

    def test_false_selects_negative(self):
        source = (
            "witness gate truth no\n"
            "witness yesvalue 40\n"
            "witness novalue 2\n"
            "witness result settle gate yesvalue novalue\n"
            "resolve result\n"
        )
        value = execute_native_decision_ir_v1(lower_decision_graph_to_native_ir_v1(source))
        self.assertEqual((value.domain, value.value), (WHOLE, 2))

    def test_nested_settle_realizes_selected_paths(self):
        source = (
            "witness first truth yes\n"
            "witness second truth no\n"
            "witness a truth yes\n"
            "witness b truth no\n"
            "witness inner settle second a b\n"
            "witness result settle first inner a\n"
            "resolve result\n"
        )
        value = execute_native_decision_ir_v1(lower_decision_graph_to_native_ir_v1(source))
        self.assertEqual((value.domain, value.value), (TRUTH, False))

    def test_native_ir_object_graph_contains_no_legacy_ast_nodes(self):
        source = (
            "witness gate truth yes\n"
            "witness a 1\n"
            "witness b 2\n"
            "witness result settle gate a b\n"
            "resolve result\n"
        )
        ir = lower_decision_graph_to_native_ir_v1(source)
        names = {type(ir).__name__}
        for witness in ir.witnesses:
            names.add(type(witness).__name__)
            for atom in witness.atoms:
                names.add(type(atom).__name__)
        forbidden = {"Program", "GenericFunctionDeclaration", "LetStatement", "ReturnStatement", "BinaryExpression"}
        self.assertTrue(names.isdisjoint(forbidden))


if __name__ == "__main__":
    unittest.main()
