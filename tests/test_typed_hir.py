from __future__ import annotations

import unittest

from koschei.parser import parse
from koschei.semantic import SemanticError
from koschei.type_system import GenericType, NamedType, UnionType, parse_type_text, render_type
from koschei.typed_hir import check_typed_hir, lower_typed_hir


class StructuralTypeTests(unittest.TestCase):
    def test_nested_generic_union_is_structural(self) -> None:
        type_node = parse_type_text("Result<List<Int>, Error> or Void")
        self.assertIsInstance(type_node, UnionType)
        self.assertEqual(render_type(type_node), "Result<List<Int>, Error> or Void")

    def test_generic_arguments_are_nodes_not_strings(self) -> None:
        type_node = parse_type_text("Map<String, Option<Int>>")
        self.assertIsInstance(type_node, GenericType)
        self.assertEqual(type_node.name, "Map")
        self.assertEqual(type_node.arguments[0], NamedType("String"))
        self.assertIsInstance(type_node.arguments[1], GenericType)


class TypedHIRCollectionTests(unittest.TestCase):
    def test_for_variable_receives_list_element_type(self) -> None:
        program = parse(
            """
fn main() {
    let values = [1, 2, 3]
    for value in values {
        println(value + 1)
    }
}
"""
        )
        report = lower_typed_hir(program)
        self.assertIn(NamedType("Int"), report.binding_types("value"))
        self.assertEqual(report.collections, 1)

    def test_get_or_narrowing_keeps_element_type(self) -> None:
        program = parse(
            """
fn main() {
    let names = ["Ada", "Lin"]
    let first = names.get(0) or "unknown"
    println(first.trim())
}
"""
        )
        report = check_typed_hir(program)
        self.assertIn(NamedType("String"), report.binding_types("first"))

    def test_invalid_method_on_typed_for_item_is_rejected(self) -> None:
        program = parse(
            """
fn main() {
    for value in [1, 2] {
        println(value.trim())
    }
}
"""
        )
        with self.assertRaises(SemanticError) as raised:
            check_typed_hir(program)
        self.assertEqual(raised.exception.code, "KS1306")

    def test_union_collection_requires_operation_safe_for_every_member(self) -> None:
        program = parse(
            """
fn main() {
    for value in [1, "two"] {
        println(value + 1)
    }
}
"""
        )
        with self.assertRaises(SemanticError) as raised:
            check_typed_hir(program)
        self.assertEqual(raised.exception.code, "KS1306")


    def test_map_contract_is_owned_by_typed_hir(self) -> None:
        program = parse('fn main() { let values = {"name": 1} }')
        expression = program.declarations[0].body.statements[0].value
        report = check_typed_hir(program)
        resolution = report.map_literal_resolution_of(expression)
        self.assertIsNotNone(resolution)
        assert resolution is not None
        self.assertEqual(resolution.key_type, NamedType("String"))
        self.assertEqual(resolution.duplicate_policy, "reject")

    def test_map_method_identity_is_owned_by_typed_hir(self) -> None:
        program = parse(
            'fn main() { let values = {"a": 1} let x = values.contains("a") }'
        )
        call = program.declarations[0].body.statements[1].value
        report = check_typed_hir(program)
        resolution = report.map_method_resolution_of(call)
        self.assertIsNotNone(resolution)
        assert resolution is not None
        self.assertEqual(resolution.method, "contains")
        self.assertEqual(resolution.receiver_type, GenericType("Map", (NamedType("String"), NamedType("Int"))))

    def test_typed_hir_rejects_non_string_map_key(self) -> None:
        program = parse('fn main() { let values = {1: "bad"} }')
        with self.assertRaises(SemanticError) as raised:
            check_typed_hir(program)
        self.assertEqual(raised.exception.code, "KS1301")

    def test_typed_hir_rejects_duplicate_literal_map_key(self) -> None:
        program = parse(
            'fn main() { let values = {"name": "Ali", "name": "Veli"} }'
        )
        with self.assertRaises(SemanticError) as raised:
            check_typed_hir(program)
        self.assertEqual(raised.exception.code, "KS1501")


if __name__ == "__main__":
    unittest.main()
