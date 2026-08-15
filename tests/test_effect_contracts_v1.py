from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from koschei.diagnostics import lookup as lookup_diagnostic
from koschei.effect_contracts_v1 import infer_effect_contracts
from koschei.formatter import format_source
from koschei.modules import check_graph, imported_modules, load_graph
from koschei.parser import parse
from koschei.semantic import SemanticError
from koschei.typed_hir import check_typed_hir


class PureSyntaxTests(unittest.TestCase):
    def test_parser_records_pure_contract(self) -> None:
        program = parse("pure fn add(a: Int, b: Int) -> Int { return a + b }")
        self.assertEqual(len(program.declarations), 1)
        self.assertTrue(program.declarations[0].is_pure)
        self.assertEqual(program.declarations[0].name, "add")

    def test_ordinary_function_remains_uncontracted(self) -> None:
        program = parse("fn add(a: Int, b: Int) -> Int { return a + b }")
        self.assertFalse(program.declarations[0].is_pure)

    def test_formatter_preserves_pure_keyword(self) -> None:
        formatted = format_source(
            "pure   fn add(a:Int,b:Int)->Int{return a+b}\n"
        )
        self.assertIn("pure fn add", formatted)
        self.assertEqual(format_source(formatted), formatted)


class PureEffectContractTests(unittest.TestCase):
    @staticmethod
    def _check(source: str):
        with tempfile.TemporaryDirectory(prefix="koschei-effects-") as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            return check_graph(graph)

    def test_pure_arithmetic_and_immutable_value_methods_pass(self) -> None:
        self._check(
            """
pure fn normalize(value: String) -> String {
    return value.trim()
}

pure fn total(a: Int, b: Int) -> Int {
    return a + b
}

fn main() {
    println(total(20, 22))
    println(normalize("  K  "))
}
"""
        )

    def test_pure_console_write_fails(self) -> None:
        source = """
pure fn bad(value: Int) {
    println(value)
}

fn main() {}
"""
        with self.assertRaisesRegex(SemanticError, "KS3940.*console.write"):
            self._check(source)

    def test_pure_authority_input_fails_even_without_io(self) -> None:
        source = """
pure fn bad(authority: NetCaps) -> Int {
    return 1
}

fn main() {}
"""
        with self.assertRaisesRegex(SemanticError, "KS3940.*authority.input"):
            self._check(source)

    def test_pure_network_effect_fails(self) -> None:
        source = """
pure fn bad(authority: NetCaps) -> Int {
    let response = authority.get("https://example.com") or return 0
    return response.status()
}

fn main() {}
"""
        with self.assertRaisesRegex(SemanticError, "KS3940"):
            self._check(source)

    def test_pure_local_transitive_effect_fails(self) -> None:
        source = """
fn noisy(value: Int) -> Int {
    println(value)
    return value
}

pure fn calculate(value: Int) -> Int {
    return noisy(value)
}

fn main() {}
"""
        with self.assertRaisesRegex(SemanticError, "KS3940.*console.write"):
            self._check(source)

    def test_unannotated_effectful_function_remains_legal(self) -> None:
        self._check(
            """
fn noisy(value: Int) -> Int {
    println(value)
    return value
}

fn main() {
    println(noisy(7))
}
"""
        )

    def test_pure_shared_queue_observation_fails(self) -> None:
        source = """
pure fn inspect(q: BoundedQueue<Int>) -> Int {
    return queue_len(q)
}

fn main() {}
"""
        with self.assertRaisesRegex(SemanticError, "KS3940.*shared-memory.queue"):
            self._check(source)

    def test_pure_task_scheduling_fails(self) -> None:
        source = """
pure fn bad() -> Int {
    let scope = task_scope(2) or return 0
    return task_capacity(scope)
}

fn main() {}
"""
        with self.assertRaisesRegex(SemanticError, "KS3940.*concurrency.task"):
            self._check(source)

    def test_effect_report_is_sorted_and_transitive(self) -> None:
        source = """
fn leaf(value: Int) -> Int {
    println(value)
    return value
}

fn middle(value: Int) -> Int {
    return leaf(value)
}

fn main() {
    println(middle(1))
}
"""
        with tempfile.TemporaryDirectory(prefix="koschei-effects-report-") as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            module = graph.root_module
            imports = imported_modules(graph, module)
            typed = check_typed_hir(module.program, imports)
            report = infer_effect_contracts(module.program, imports, typed)
            self.assertEqual(report["leaf"].effects, ("console.write",))
            self.assertEqual(report["middle"].effects, ("console.write",))
            self.assertEqual(report["middle"].direct_calls, ("leaf",))

    def test_effect_diagnostic_is_explainable(self) -> None:
        self.assertIsNotNone(lookup_diagnostic("KS3940", "tr"))
        self.assertIsNotNone(lookup_diagnostic("KS3940", "en"))


class CrossModuleEffectTests(unittest.TestCase):
    def test_pure_import_cannot_hide_transitive_console_effect(self) -> None:
        with tempfile.TemporaryDirectory(prefix="koschei-effects-module-") as directory:
            root = Path(directory)
            (root / "dep.ks").write_text(
                """
fn noisy(value: Int) -> Int {
    println(value)
    return value
}
""",
                encoding="utf-8",
            )
            (root / "main.ks").write_text(
                """
import dep

pure fn calculate(value: Int) -> Int {
    return dep.noisy(value)
}

fn main() {}
""",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SemanticError, "KS3940.*console.write"):
                check_graph(load_graph(root / "main.ks"))

    def test_pure_import_may_call_inferred_effect_free_function(self) -> None:
        with tempfile.TemporaryDirectory(prefix="koschei-effects-module-") as directory:
            root = Path(directory)
            (root / "dep.ks").write_text(
                """
fn add(a: Int, b: Int) -> Int {
    return a + b
}
""",
                encoding="utf-8",
            )
            (root / "main.ks").write_text(
                """
import dep

pure fn calculate(value: Int) -> Int {
    return dep.add(value, 1)
}

fn main() {
    println(calculate(41))
}
""",
                encoding="utf-8",
            )
            check_graph(load_graph(root / "main.ks"))


if __name__ == "__main__":
    unittest.main()
