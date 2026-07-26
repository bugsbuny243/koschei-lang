from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from koschei.integrity import check_program_integrity
from koschei.modules import ModuleError, load_graph, require_entrypoint
from koschei.parser import parse
from koschei.semantic import SemanticError, check


class TopLevelIntegrityTests(unittest.TestCase):
    def assert_semantic_code(self, source: str, code: str) -> None:
        with self.assertRaises(SemanticError) as context:
            program = parse(source)
            check_program_integrity(program)
            check(program)
        self.assertEqual(context.exception.code, code)

    def test_duplicate_functions_are_rejected_before_backend(self) -> None:
        self.assert_semantic_code(
            "fn value() -> Int { return 1 } "
            "fn value() -> Int { return 2 } "
            "fn main() { return }",
            "KS1102",
        )

    def test_duplicate_structs_are_rejected_before_backend(self) -> None:
        self.assert_semantic_code(
            "struct Box { value: Int } "
            "struct Box { value: String } "
            "fn main() { return }",
            "KS1102",
        )

    def test_duplicate_enums_are_rejected_before_backend(self) -> None:
        self.assert_semantic_code(
            "enum State { Ready } enum State { Waiting } fn main() { return }",
            "KS1102",
        )

    def test_struct_and_enum_name_collision_is_rejected(self) -> None:
        self.assert_semantic_code(
            "struct State { value: Int } enum State { Ready } fn main() { return }",
            "KS1701",
        )


class ReturnFlowIntegrityTests(unittest.TestCase):
    def assert_semantic_code(self, source: str, code: str) -> None:
        with self.assertRaises(SemanticError) as context:
            program = parse(source)
            check_program_integrity(program)
            check(program)
        self.assertEqual(context.exception.code, code)

    def test_non_void_function_must_return_on_every_path(self) -> None:
        self.assert_semantic_code(
            "fn answer(flag: Bool) -> Int { if flag { return 42 } }",
            "KS1303",
        )

    def test_if_else_returning_on_both_paths_is_accepted(self) -> None:
        program = parse(
            "fn answer(flag: Bool) -> Int { "
            "if flag { return 42 } else { return 0 } "
            "} fn main() { return }"
        )
        check_program_integrity(program)
        report = check(program)
        self.assertEqual(report.functions, 2)

    def test_else_if_chain_must_be_exhaustive(self) -> None:
        self.assert_semantic_code(
            "fn classify(value: Int) -> String { "
            'if value < 0 { return "negative" } '
            'else if value == 0 { return "zero" } '
            "}",
            "KS1303",
        )

    def test_void_function_cannot_return_a_value(self) -> None:
        self.assert_semantic_code("fn helper() { return 7 }", "KS1304")

    def test_unreachable_statement_after_return_is_rejected(self) -> None:
        self.assert_semantic_code(
            'fn answer() -> Int { return 42 println("never") }',
            "KS1305",
        )

    def test_unreachable_statement_after_exhaustive_if_is_rejected(self) -> None:
        self.assert_semantic_code(
            "fn answer(flag: Bool) -> Int { "
            "if flag { return 1 } else { return 2 } "
            "return 3 }",
            "KS1305",
        )


class BinaryTargetIntegrityTests(unittest.TestCase):
    def test_library_graph_can_be_checked_without_main(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "math.ks"
            path.write_text(
                "fn add(a: Int, b: Int) -> Int { return a + b }",
                encoding="utf-8",
            )
            graph = load_graph(path)
            with self.assertRaises(ModuleError) as context:
                require_entrypoint(graph)
        self.assertEqual(context.exception.code, "KS1801")

    def test_valid_main_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text("fn main() { return }", encoding="utf-8")
            require_entrypoint(load_graph(path))

    def test_main_cannot_declare_a_return_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text("fn main() -> Int { return 0 }", encoding="utf-8")
            graph = load_graph(path)
            with self.assertRaises(ModuleError) as context:
                require_entrypoint(graph)
        self.assertEqual(context.exception.code, "KS1801")


if __name__ == "__main__":
    unittest.main()
