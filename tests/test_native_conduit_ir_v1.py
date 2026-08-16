from __future__ import annotations

import unittest

from koschei.native_conduit_ir_v1 import (
    NativeConduitIrError,
    compose_reusable_and_root_native_ir_v1,
    execute_conduit_source_native_ir_v1,
    lower_conduit_source_to_native_ir_v1,
)
from koschei.native_value_domains_v1 import GLYPHS, TRUTH, WHOLE, NativeValue


class NativeConduitIrV1Tests(unittest.TestCase):
    def test_whole_reusable_and_root_execute_without_legacy_ast(self):
        reusable = "witness left conduit 0\nwitness right conduit 1\nwitness total sum left right\nresolve total\n"
        root = "witness value conduit 0\nresolve value\n"
        result = compose_reusable_and_root_native_ir_v1(
            reusable,
            {0: NativeValue(WHOLE, 40), 1: NativeValue(WHOLE, 2)},
            root,
            root_slot=0,
        )
        self.assertEqual((result.domain, result.value), (WHOLE, 42))

    def test_mixed_truth_and_glyphs_inputs_execute_natively(self):
        source = (
            "witness approved conduit 0\n"
            "witness label conduit 1\n"
            "witness expected glyphs 2 ok\n"
            "witness labelok same label expected\n"
            "witness result same approved labelok\n"
            "resolve result\n"
        )
        value = execute_conduit_source_native_ir_v1(
            source,
            {0: NativeValue(TRUTH, True), 1: NativeValue(GLYPHS, "ok")},
        )
        self.assertEqual((value.domain, value.value), (TRUTH, True))

    def test_slot_set_must_match_exactly(self):
        source = "witness left conduit 0\nwitness right conduit 1\nwitness total sum left right\nresolve total\n"
        with self.assertRaisesRegex(NativeConduitIrError, "exactly match"):
            lower_conduit_source_to_native_ir_v1(source, {0: NativeValue(WHOLE, 1)})

    def test_conduit_ir_object_graph_contains_no_legacy_ast_nodes(self):
        source = "witness left conduit 0\nwitness total sum left 2\nresolve total\n"
        ir = lower_conduit_source_to_native_ir_v1(source, {0: NativeValue(WHOLE, 40)})
        forbidden = {"Program", "GenericFunctionDeclaration", "LetStatement", "ReturnStatement", "BinaryExpression"}
        seen = {type(ir).__name__}
        for witness in ir.witnesses:
            seen.add(type(witness).__name__)
            for atom in witness.atoms:
                seen.add(type(atom).__name__)
        self.assertFalse(forbidden & seen)

    def test_conduit_source_is_not_function_parameter_syntax(self):
        source = "witness value conduit 0\nresolve value\n"
        ir = lower_conduit_source_to_native_ir_v1(source, {0: NativeValue(GLYPHS, "sealed")})
        self.assertEqual(len(ir.witnesses), 1)
        self.assertEqual(ir.witnesses[0].name, "value")
        self.assertEqual(ir.witnesses[0].atoms[0].literal, NativeValue(GLYPHS, "sealed"))


if __name__ == "__main__":
    unittest.main()
