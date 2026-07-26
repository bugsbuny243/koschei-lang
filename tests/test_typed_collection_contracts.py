from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from koschei.modules import check_graph, load_graph
from koschei.semantic import SemanticError


class PublicTypedCollectionContractTests(unittest.TestCase):
    def compile(self, source: str) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            check_graph(load_graph(path))

    def assert_code(self, source: str, code: str) -> None:
        with self.assertRaises(SemanticError) as raised:
            self.compile(source)
        self.assertEqual(raised.exception.code, code)

    def test_list_parameter_accepts_matching_literal(self) -> None:
        self.compile(
            "fn sum(values: List<Int>) -> Int { "
            "let mut total = 0 for value in values { total = total + value } "
            "return total } fn main() { println(sum([1, 2, 3])) }"
        )

    def test_list_parameter_rejects_wrong_element_type(self) -> None:
        self.assert_code(
            'fn sum(values: List<Int>) -> Int { return 0 } '
            'fn main() { println(sum([1, "two"])) }',
            "KS1301",
        )

    def test_list_return_contract_is_checked(self) -> None:
        self.compile(
            'fn names() -> List<String> { return ["Ada", "Lin"] } '
            'fn main() { println(names()) }'
        )
        self.assert_code(
            'fn names() -> List<String> { return ["Ada", 2] } fn main() {}',
            "KS1301",
        )

    def test_nested_collection_annotations_are_supported(self) -> None:
        self.compile(
            'fn rows() -> List<Map<String, Int>> { '
            'return [{"count": 1}, {"count": 2}] } '
            'fn main() { println(rows()) }'
        )

    def test_struct_field_preserves_collection_contract(self) -> None:
        self.compile(
            'struct Batch { ids: List<Int> } '
            'fn main() { let batch = Batch { ids: [1, 2] } println(batch.ids) }'
        )
        self.assert_code(
            'struct Batch { ids: List<Int> } '
            'fn main() { let batch = Batch { ids: [1, "x"] } println(batch.ids) }',
            "KS1301",
        )

    def test_enum_payload_preserves_map_contract(self) -> None:
        self.compile(
            'enum Event { Counts(Map<String, Int>) } '
            'fn main() { let event = Counts({"ok": 1}) println(event) }'
        )
        self.assert_code(
            'enum Event { Counts(Map<String, Int>) } '
            'fn main() { let event = Counts({"ok": "yes"}) println(event) }',
            "KS1301",
        )

    def test_for_binding_receives_declared_element_type(self) -> None:
        self.compile(
            'fn print_names(values: List<String>) { '
            'for value in values { println(value.trim()) } } fn main() {}'
        )
        self.assert_code(
            'fn broken(values: List<Int>) { '
            'for value in values { println(value.trim()) } } fn main() {}',
            "KS1306",
        )

    def test_get_and_or_keep_collection_value_contract(self) -> None:
        self.compile(
            'fn first(values: List<String>) -> String { '
            'return values.get(0) or "missing" } '
            'fn port(values: Map<String, Int>) -> Int { '
            'return values.get("port") or 8080 } fn main() {}'
        )

    def test_map_parameter_rejects_wrong_value_type(self) -> None:
        self.assert_code(
            'fn port(values: Map<String, Int>) -> Int { return 0 } '
            'fn main() { println(port({"port": "8080"})) }',
            "KS1301",
        )

    def test_map_key_type_is_fixed_to_string(self) -> None:
        self.assert_code('fn bad(values: Map<Int, String>) {}', "KS1301")

    def test_collections_cannot_hide_capabilities(self) -> None:
        for source in (
            'fn hide(values: List<NetCaps>) {}',
            'fn hide(values: Map<String, DiskCaps>) {}',
            'struct Hidden { values: List<DiskReadCaps> }',
            'enum Hidden { Values(Map<String, EnvCaps>) }',
        ):
            with self.subTest(source=source):
                self.assert_code(source, "KS2402")

    def test_raw_v09_collection_annotations_remain_compatible(self) -> None:
        self.compile(
            'fn old_list(values: List) { println(values) } '
            'fn old_map(values: Map) { println(values) } '
            'fn main() { old_list([1, "x"]) old_map({"x": 1}) }'
        )

    def test_typed_contracts_cross_module_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.ks").write_text(
                'fn total(values: List<Int>) -> Int { return 0 }',
                encoding="utf-8",
            )
            main = root / "main.ks"
            main.write_text(
                'import data fn main() { println(data.total([1, 2])) }',
                encoding="utf-8",
            )
            check_graph(load_graph(main))
            main.write_text(
                'import data fn main() { println(data.total([1, "x"])) }',
                encoding="utf-8",
            )
            with self.assertRaises(SemanticError) as raised:
                check_graph(load_graph(main))
            self.assertEqual(raised.exception.code, "KS1301")


if __name__ == "__main__":
    unittest.main()
