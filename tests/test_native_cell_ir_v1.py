from __future__ import annotations

from dataclasses import replace
import unittest

from koschei.native_cell_ir_v1 import (
    NativeCellIrError,
    execute_checked_cell_projection_native_ir_v1,
    feed_checked_cell_projection_to_conduit_ir_v1,
    lower_checked_cell_projection_to_native_ir_v1,
)
from koschei.native_cell_projection_v1 import NativeCellProjectionCheckV1
from koschei.native_ir_v1 import execute_native_ir_v1
from koschei.native_value_domains_v1 import GLYPHS, TRUTH, WHOLE, NativeValue


class NativeCellIrV1Tests(unittest.TestCase):
    def _checked(self, value: NativeValue, *, ordinal: int = 1) -> NativeCellProjectionCheckV1:
        cells = (
            NativeValue(WHOLE, 40),
            value,
            NativeValue(TRUTH, True),
        )
        return NativeCellProjectionCheckV1(
            schema_id=b"s" * 16,
            ordered_witnesses=("amount", "selected", "approved"),
            dependency_order=("amount", "selected", "approved"),
            values={"amount": cells[0], "selected": cells[1], "approved": cells[2]},
            cells=cells,
            selected_ordinal=ordinal,
            selected_value=cells[ordinal],
            lowered=None,  # compatibility carrier is deliberately irrelevant here
            semantic=None,
        )

    def test_checked_cell_scalar_executes_directly_on_native_ir(self):
        checked = self._checked(NativeValue(GLYPHS, "paid"))
        projected = lower_checked_cell_projection_to_native_ir_v1(checked)
        self.assertEqual(projected.selected_ordinal, 1)
        self.assertEqual(execute_checked_cell_projection_native_ir_v1(checked), NativeValue(GLYPHS, "paid"))

    def test_checked_cell_feeds_reusable_conduit_without_member_or_index_model(self):
        checked = self._checked(NativeValue(WHOLE, 2))
        source = "witness fee conduit 0\nwitness base 40\nwitness total sum base fee\nresolve total\n"
        ir = feed_checked_cell_projection_to_conduit_ir_v1(checked, source=source)
        self.assertEqual(execute_native_ir_v1(ir), NativeValue(WHOLE, 42))

    def test_selected_value_must_match_proven_full_schema(self):
        checked = self._checked(NativeValue(WHOLE, 2))
        tampered = replace(checked, selected_value=NativeValue(WHOLE, 9))
        with self.assertRaisesRegex(NativeCellIrError, "full schema"):
            lower_checked_cell_projection_to_native_ir_v1(tampered)

    def test_invalid_schema_identity_is_rejected(self):
        checked = self._checked(NativeValue(WHOLE, 2))
        tampered = replace(checked, schema_id=b"\\x00" * 16)
        with self.assertRaisesRegex(NativeCellIrError, "schema identity"):
            lower_checked_cell_projection_to_native_ir_v1(tampered)

    def test_native_cell_ir_object_graph_has_no_legacy_ast_carrier(self):
        checked = self._checked(NativeValue(TRUTH, True))
        projected = lower_checked_cell_projection_to_native_ir_v1(checked)
        names = {type(projected.ir).__name__}
        names.update(type(item).__name__ for item in projected.ir.witnesses)
        names.update(type(atom).__name__ for item in projected.ir.witnesses for atom in item.atoms)
        forbidden = {"Program", "GenericFunctionDeclaration", "LetStatement", "ReturnStatement", "BinaryExpression"}
        self.assertTrue(names.isdisjoint(forbidden))


if __name__ == "__main__":
    unittest.main()
