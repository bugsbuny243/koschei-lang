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
from koschei.interpreter import Interpreter, KoscheiRuntimeError
from koschei.modules import check_graph, load_graph
from koschei.parser import parse
from koschei.semantic import SemanticError
from koschei.type_system import GenericType, NamedType
from koschei.typed_hir import check_typed_hir

GO = shutil.which("go")


class GenericAggregateParserTests(unittest.TestCase):
    def test_parser_records_struct_and_enum_type_parameters(self) -> None:
        program = parse(
            "struct Pair<T, U> { left: T, right: U } "
            "enum Maybe<T> { Present(T), Missing }"
        )
        self.assertEqual(program.structs[0].type_parameters, ("T", "U"))
        self.assertEqual(program.enums[0].type_parameters, ("T",))

    def test_formatter_compacts_generic_aggregate_headers(self) -> None:
        source = "struct Box < T > {value:T} enum Maybe < T > {Present(T),Missing}"
        self.assertEqual(
            format_source(source),
            "struct Box<T> {\n"
            "    value: T\n"
            "}\n"
            "enum Maybe<T> {\n"
            "    Present(T), Missing\n"
            "}\n",
        )


class GenericStructInferenceTests(unittest.TestCase):
    def test_struct_literal_infers_type_and_field_substitution(self) -> None:
        report = check_typed_hir(
            parse(
                """
struct Box<T> { value: T }
fn main() {
    let box = Box { value: 41 }
    println(box.value + 1)
}
"""
            )
        )
        self.assertIn(
            GenericType("Box", (NamedType("Int"),)),
            report.binding_types("box"),
        )

    def test_multiple_struct_parameters_are_inferred_independently(self) -> None:
        report = check_typed_hir(
            parse(
                """
struct Pair<T, U> { left: T, right: U }
fn main() {
    let pair = Pair { left: "Ada", right: 42 }
    println(pair.left.trim())
    println(pair.right + 1)
}
"""
            )
        )
        self.assertIn(
            GenericType(
                "Pair", (NamedType("String"), NamedType("Int"))
            ),
            report.binding_types("pair"),
        )

    def test_conflicting_struct_evidence_is_rejected(self) -> None:
        program = parse(
            'struct Same<T> { left: T, right: T } '
            'fn main() { let bad = Same { left: 1, right: "two" } }'
        )
        with self.assertRaises(SemanticError) as raised:
            check_typed_hir(program)
        self.assertEqual(raised.exception.code, "KS1307")

    def test_raw_generic_struct_annotation_is_rejected(self) -> None:
        program = parse(
            "struct Box<T> { value: T } fn read(box: Box) -> Int { return 0 }"
        )
        with self.assertRaises(SemanticError) as raised:
            check_typed_hir(program)
        self.assertEqual(raised.exception.code, "KS1307")

    def test_generic_struct_arity_is_checked(self) -> None:
        program = parse(
            "struct Pair<T, U> { left: T, right: U } "
            "fn read(pair: Pair<Int>) -> Int { return 0 }"
        )
        with self.assertRaises(SemanticError) as raised:
            check_typed_hir(program)
        self.assertEqual(raised.exception.code, "KS1301")

    def test_unused_aggregate_type_parameter_is_rejected(self) -> None:
        program = parse("struct Marker<T> { value: Int }")
        with self.assertRaises(SemanticError) as raised:
            check_typed_hir(program)
        self.assertEqual(raised.exception.code, "KS1307")

    def test_map_key_parameter_is_allowed_but_concrete_key_stays_string(self) -> None:
        report = check_typed_hir(
            parse(
                """
struct Cache<K, V> { entries: Map<K, V> }
fn main() {
    let cache = Cache { entries: {"port": 8080} }
    println(cache.entries.get("port") or 0)
}
"""
            )
        )
        self.assertIn(
            GenericType(
                "Cache", (NamedType("String"), NamedType("Int"))
            ),
            report.binding_types("cache"),
        )


class GenericEnumInferenceTests(unittest.TestCase):
    def test_payload_constructor_and_match_preserve_type(self) -> None:
        report = check_typed_hir(
            parse(
                """
enum Maybe<T> { Present(T), Missing }
fn main() {
    let item = Present("Ada")
    let name = match item {
        Present(value) => value,
        Missing => "none",
    }
    println(name.trim())
}
"""
            )
        )
        self.assertIn(
            GenericType("Maybe", (NamedType("String"),)),
            report.binding_types("item"),
        )
        self.assertIn(NamedType("String"), report.binding_types("value"))

    def test_payloadless_variant_can_flow_into_concrete_return_contract(self) -> None:
        source = """
enum Maybe<T> { Present(T), Missing }
fn missing() -> Maybe<Int> { return Missing() }
fn main() {
    let item = missing()
    let value = match item {
        Present(number) => number,
        Missing => 0,
    }
    println(value + 1)
}
"""
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            check_graph(load_graph(path))
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["run", str(path)])
            self.assertEqual(code, 0)
            self.assertEqual(output.getvalue(), "1\n")

    def test_runtime_generic_enum_rejects_capability_payload(self) -> None:
        from koschei.interpreter import NetCaps
        from koschei.ast_nodes import SourceLocation

        program = parse("enum Maybe<T> { Present(T), Missing }")
        interpreter = Interpreter(program, [])
        constructor = interpreter.constructors["Present"]
        with self.assertRaises(KoscheiRuntimeError) as raised:
            interpreter._invoke(
                constructor,
                [NetCaps("https://example.com")],
                SourceLocation(1, 1),
            )
        self.assertEqual(raised.exception.code, "KS3401")


class GenericAggregateSecurityTests(unittest.TestCase):
    def assert_code(self, source: str, code: str) -> None:
        with self.assertRaises(SemanticError) as raised:
            check_typed_hir(parse(source))
        self.assertEqual(raised.exception.code, code)

    def test_capability_cannot_bind_to_generic_struct_slot(self) -> None:
        self.assert_code(
            """
struct Box<T> { value: T }
fn main(caps: SystemCaps) {
    let net = caps.net.allow("https://example.com")
    let hidden = Box { value: net }
}
""",
            "KS2402",
        )

    def test_capability_cannot_bind_to_generic_enum_slot(self) -> None:
        self.assert_code(
            """
enum Maybe<T> { Present(T), Missing }
fn main(caps: SystemCaps) {
    let net = caps.net.allow("https://example.com")
    let hidden = Present(net)
}
""",
            "KS2402",
        )

    def test_capability_generic_annotation_is_rejected(self) -> None:
        self.assert_code(
            "struct Box<T> { value: T } fn hide(value: Box<NetCaps>) {}",
            "KS2402",
        )

    def test_runtime_conflicting_struct_evidence_is_not_security_telemetry(self) -> None:
        program = parse(
            'struct Same<T> { left: T, right: T } '
            'fn main() { let bad = Same { left: 1, right: "two" } }'
        )
        with self.assertRaises(KoscheiRuntimeError) as raised:
            Interpreter(program, []).execute_main()
        self.assertEqual(raised.exception.code, "KS3106")
        self.assertIn("capability ihlali değildir", raised.exception.message)


class GenericAggregatePipelineTests(unittest.TestCase):
    SOURCE = """
struct Box<T> { value: T }
enum Maybe<T> { Present(T), Missing }
fn boxed(value: Int) -> Box<Int> { return Box { value: value } }
fn named(value: String) -> Maybe<String> { return Present(value) }
fn main() {
    let box = boxed(9)
    let item = named("Ada")
    let name = match item {
        Present(value) => value,
        Missing => "none",
    }
    println(box.value + 1)
    println(name.trim())
}
"""

    def test_check_and_interpreter_keep_aggregate_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / "main.ks"
            source.write_text(self.SOURCE, encoding="utf-8")
            check_graph(load_graph(source))
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["run", str(source)])
            self.assertEqual(code, 0)
            self.assertEqual(output.getvalue(), "10\nAda\n")

    def test_imported_generic_struct_and_enum_keep_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "types.ks").write_text(
                "struct Box<T> { value: T }\n"
                "enum Maybe<T> { Present(T), Missing }\n"
                "fn boxed(value: Int) -> Box<Int> { return Box { value: value } }\n"
                "fn named(value: String) -> Maybe<String> { return Present(value) }\n",
                encoding="utf-8",
            )
            source = root / "main.ks"
            source.write_text(
                "import types\n"
                "fn main() {\n"
                "    let box = types.boxed(9)\n"
                "    let item = types.named(\"Ada\")\n"
                "    let name = match item {\n"
                "        Present(value) => value,\n"
                "        Missing => \"none\",\n"
                "    }\n"
                "    println(box.value + 1)\n"
                "    println(name.trim())\n"
                "}\n",
                encoding="utf-8",
            )
            check_graph(load_graph(source))
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["run", str(source)])
            self.assertEqual(code, 0)
            self.assertEqual(output.getvalue(), "10\nAda\n")

    @unittest.skipUnless(GO, "Go toolchain is required")
    def test_native_generic_aggregates_match_interpreter(self) -> None:
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
            self.assertEqual(run.stdout, "10\nAda\n")


if __name__ == "__main__":
    unittest.main()
