from __future__ import annotations

import unittest

from koschei.ast_nodes import BinaryExpression, LetStatement, Literal
from koschei.native_value_domains_v1 import check_native_value_domains


class NativeValueDomainBackendMaterializationV1Tests(unittest.TestCase):
    def _function(self, checked):
        self.assertEqual(len(checked.lowered.declarations), 1)
        return checked.lowered.declarations[0]

    def _assert_all_witnesses_materialized(self, source: str) -> None:
        checked = check_native_value_domains(source)
        function = self._function(checked)
        witness_statements = [
            statement
            for statement in function.body.statements
            if isinstance(statement, LetStatement)
        ]
        self.assertEqual(len(witness_statements), len(checked.graph.witnesses))
        self.assertTrue(witness_statements)
        for statement in witness_statements:
            self.assertIsInstance(statement.value, Literal)
            self.assertNotIsInstance(statement.value, BinaryExpression)
            canonical = checked.values[statement.name]
            self.assertEqual(statement.value.value, canonical.value)

    def test_derived_whole_truth_and_glyphs_are_canonical_literals_below_frontend(self) -> None:
        self._assert_all_witnesses_materialized(
            "witness base 40\n"
            "witness fee 2\n"
            "witness total sum base fee\n"
            "resolve total\n"
        )
        self._assert_all_witnesses_materialized(
            "witness left 42\n"
            "witness right 42\n"
            "witness equal same left right\n"
            "resolve equal\n"
        )
        self._assert_all_witnesses_materialized(
            "witness base glyphs 1 e\n"
            "witness mark glyphs 2 \u0301\n"
            "witness joined merge base mark\n"
            "resolve joined\n"
        )

    def test_closed_graph_materialization_preserves_dependency_order(self) -> None:
        checked = check_native_value_domains(
            "witness answer sum left right\n"
            "witness right 2\n"
            "witness left 40\n"
            "resolve answer\n"
        )
        function = self._function(checked)
        lowered_names = tuple(
            statement.name
            for statement in function.body.statements
            if isinstance(statement, LetStatement)
        )
        self.assertEqual(lowered_names, checked.dependency_order)
        self.assertEqual(checked.value.value, 42)


if __name__ == "__main__":
    unittest.main()