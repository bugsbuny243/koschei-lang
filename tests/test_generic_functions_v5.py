from __future__ import annotations

import io
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout

from koschei.cli import main
from koschei.formatter import format_source
from koschei.modules import check_graph, load_graph
from koschei.parser import parse
from koschei.semantic import SemanticError
from koschei.type_system import NamedType
from koschei.typed_hir import check_typed_hir

GO = shutil.which("go")


class GenericFunctionParserTests(unittest.TestCase):
    def test_parser_records_declared_type_parameters(self) -> None:
        function = parse(
            "fn identity<T>(value: T) -> T { return value }"
        ).declarations[0]
        self.assertEqual(function.type_parameters, ("T",))
        self.assertEqual(function.parameters[0].type_ref.names, ("T",))

    def test_formatter_compacts_generic_function_header(self) -> None:
        source = "fn identity < T > (value:T)->T{return value}"
        self.assertEqual(
            format_source(source),
            "fn identity<T>(value: T) -> T {\n    return value\n}\n",
        )


class GenericFunctionInferenceTests(unittest.TestCase):
    def test_identity_result_is_inferred_at_call_site(self) -> None:
        report = check_typed_hir(
            parse(
                """
fn identity<T>(value: T) -> T {
    return value
}
fn main() {
    let answer = identity(42)
    println(answer + 1)
}
"""
            )
        )
        self.assertIn(NamedType("Int"), report.binding_types("answer"))

    def test_multiple_type_parameters_are_inferred_independently(self) -> None:
        report = check_typed_hir(
            parse(
                """
fn choose_left<T, U>(left: T, right: U) -> T { return left }
fn main() {
    let value = choose_left("Ada", 42)
    println(value.trim())
}
"""
            )
        )
        self.assertIn(NamedType("String"), report.binding_types("value"))

    def test_generic_option_result_is_substituted(self) -> None:
        report = check_typed_hir(
            parse(
                """
fn wrap<T>(value: T) -> Option<T> { return Some(value) }
fn main() {
    let wrapped = wrap(42)
    let answer = wrapped or 0
    println(answer + 1)
}
"""
            )
        )
        self.assertIn(NamedType("Int"), report.binding_types("answer"))

    def test_nested_list_type_is_substituted(self) -> None:
        report = check_typed_hir(
            parse(
                """
fn head_or<T>(values: List<T>, fallback: T) -> T {
    return values.get(0) or fallback
}
fn main() {
    let name = head_or(["Ada"], "none")
    println(name.trim())
}
"""
            )
        )
        self.assertIn(NamedType("String"), report.binding_types("name"))

    def test_conflicting_evidence_is_rejected(self) -> None:
        program = parse(
            """
fn same<T>(left: T, right: T) -> T { return left }
fn main() { println(same(1, "two")) }
"""
        )
        with self.assertRaises(SemanticError) as raised:
            check_typed_hir(program)
        self.assertEqual(raised.exception.code, "KS1307")

    def test_result_only_type_parameter_is_rejected(self) -> None:
        program = parse(
            """
fn impossible<T>() -> Option<T> { return None() }
fn main() { println(impossible()) }
"""
        )
        with self.assertRaises(SemanticError) as raised:
            check_typed_hir(program)
        self.assertEqual(raised.exception.code, "KS1307")

    def test_duplicate_type_parameter_is_rejected(self) -> None:
        program = parse(
            "fn identity<T, T>(value: T) -> T { return value }"
        )
        with self.assertRaises(SemanticError) as raised:
            check_typed_hir(program)
        self.assertEqual(raised.exception.code, "KS1307")

    def test_main_cannot_be_generic(self) -> None:
        program = parse("fn main<T>() {}")
        with self.assertRaises(SemanticError) as raised:
            check_typed_hir(program)
        self.assertEqual(raised.exception.code, "KS1307")

    def test_capability_cannot_bind_to_generic_parameter(self) -> None:
        program = parse(
            """
fn identity<T>(value: T) -> T { return value }
fn main(caps: SystemCaps) {
    let net = caps.net.allow("https://example.com")
    let hidden = identity(net)
}
"""
        )
        with self.assertRaises(SemanticError) as raised:
            check_typed_hir(program)
        self.assertEqual(raised.exception.code, "KS2402")


class GenericFunctionPipelineTests(unittest.TestCase):
    SOURCE = """
fn identity<T>(value: T) -> T {
    return value
}

fn head_or<T>(values: List<T>, fallback: T) -> T {
    return values.get(0) or fallback
}

fn main() {
    let number = identity(7)
    let name = head_or(["Ada", "Lin"], "none")
    println(number + 1)
    println(name.trim())
}
"""

    def test_check_and_interpreter_keep_generic_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / "main.ks"
            source.write_text(self.SOURCE, encoding="utf-8")
            check_graph(load_graph(source))
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["run", str(source)])
            self.assertEqual(code, 0)
            self.assertEqual(output.getvalue(), "8\nAda\n")

    def test_imported_generic_function_is_inferred(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "tools.ks").write_text(
                "fn identity<T>(value: T) -> T { return value }\n",
                encoding="utf-8",
            )
            source = root / "main.ks"
            source.write_text(
                'import tools\nfn main() { let value = tools.identity("Ada") println(value.trim()) }\n',
                encoding="utf-8",
            )
            check_graph(load_graph(source))
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["run", str(source)])
            self.assertEqual(code, 0)
            self.assertEqual(output.getvalue(), "Ada\n")

    @unittest.skipUnless(GO, "Go toolchain is required")
    def test_native_generic_program_matches_interpreter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source = root / "main.ks"
            binary = root / "app"
            source.write_text(self.SOURCE, encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["build", str(source), "-o", str(binary)])
            self.assertEqual(code, 0)
            run = subprocess.run(
                [str(binary)], capture_output=True, text=True, check=True
            )
            self.assertEqual(run.stdout, "8\nAda\n")


if __name__ == "__main__":
    unittest.main()
