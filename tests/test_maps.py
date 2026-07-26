from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from koschei.ast_nodes import MapLiteral
from koschei.capabilities import analyze
from koschei.codegen_go import CodegenError, generate_go
from koschei.diagnostics import lookup
from koschei.formatter import format_source
from koschei.interpreter import Interpreter, KoscheiRuntimeError
from koschei.lexer import tokenize
from koschei.parser import parse
from koschei.semantic import SemanticError, check


def compile_program(source: str):
    program = parse(source)
    check(program)
    return program


def run_source(source: str) -> str:
    program = compile_program(source)
    output = io.StringIO()
    with redirect_stdout(output):
        Interpreter(program, []).execute_main()
    return output.getvalue()


class MapParsingTests(unittest.TestCase):
    def test_literal_and_trailing_comma_are_parsed(self) -> None:
        program = parse(
            'fn main() { let customer = {"name": "Ali", "age": 42,} }'
        )
        statement = program.declarations[0].body.statements[0]
        self.assertIsInstance(statement.value, MapLiteral)
        self.assertEqual(len(statement.value.entries), 2)

    def test_empty_map_is_parsed_in_expression_context(self) -> None:
        program = parse("fn main() { let values = {} }")
        statement = program.declarations[0].body.statements[0]
        self.assertIsInstance(statement.value, MapLiteral)
        self.assertEqual(statement.value.entries, ())

    def test_dynamic_string_key_is_allowed(self) -> None:
        compile_program('fn main() { let key = "name" let values = {key: "Ali"} }')


class MapSemanticTests(unittest.TestCase):
    def test_map_methods_are_allowed(self) -> None:
        compile_program(
            "fn main() { "
            'let values = {"name": "Ali"} '
            'let name = values.get("name") or "yok" '
            'let updated = values.set("city", "Istanbul") '
            "let keys = updated.keys() "
            'let has = updated.contains("city") '
            "}"
        )

    def test_non_string_literal_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS1301"):
            compile_program("fn main() { let values = {1: \"Ali\"} }")

    def test_duplicate_literal_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS1501"):
            compile_program(
                'fn main() { let values = {"name": "Ali", "name": "Veli"} }'
            )

    def test_unknown_map_method_is_rejected(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS1502"):
            compile_program('fn main() { let values = {} let x = values.clear() }')

    def test_map_method_arity_is_checked(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS1301"):
            compile_program('fn main() { let values = {} let x = values.keys("x") }')

    def test_map_method_key_type_is_checked(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS1301"):
            compile_program("fn main() { let values = {} let x = values.contains(1) }")

    def test_bare_get_result_must_not_be_ignored(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS1401"):
            compile_program('fn main() { let values = {} values.get("name") }')

    def test_capability_cannot_be_stored_in_map_literal(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS2401"):
            compile_program(
                'fn main(caps: SystemCaps) { let values = {"disk": caps.disk} }'
            )

    def test_capability_cannot_be_stored_with_set(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS2401"):
            compile_program(
                "fn main(caps: SystemCaps) { "
                "let values = {} "
                'let unsafe = values.set("disk", caps.disk) '
                "}"
            )

    def test_map_type_can_cross_function_boundary(self) -> None:
        output = run_source(
            "fn read_name(values: Map) -> String { "
            'return values.get("name") or "yok" '
            "} "
            'fn main() { println(read_name({"name": "Ali"})) }'
        )
        self.assertEqual(output, "Ali\n")


class MapRuntimeTests(unittest.TestCase):
    def test_get_set_keys_and_contains(self) -> None:
        output = run_source(
            "fn main() { "
            'let original = {"name": "Ali", "age": 42} '
            'let updated = original.set("city", "Istanbul") '
            'println(updated.get("name") or "yok") '
            'println(updated.contains("city")) '
            "println(updated.keys()) "
            "println(original) "
            "println(updated) "
            "}"
        )
        self.assertEqual(
            output,
            "Ali\n"
            "true\n"
            '["name", "age", "city"]\n'
            '{"name": "Ali", "age": 42}\n'
            '{"name": "Ali", "age": 42, "city": "Istanbul"}\n',
        )

    def test_missing_key_is_an_error_value(self) -> None:
        output = run_source(
            'fn main() { let values = {} println(values.get("missing") or "yok") }'
        )
        self.assertEqual(output, "yok\n")

    def test_nested_map_and_list_render_readably(self) -> None:
        output = run_source(
            'fn main() { println({"items": [1, 2], "meta": {"ok": true}}) }'
        )
        self.assertEqual(output, '{"items": [1, 2], "meta": {"ok": true}}\n')

    def test_runtime_rejects_capability_laundering_without_semantic_check(self) -> None:
        program = parse(
            'fn main(caps: SystemCaps) { let values = {"disk": caps.disk} }'
        )
        with self.assertRaisesRegex(KoscheiRuntimeError, "KS3401"):
            Interpreter(program, []).execute_main()

    def test_dynamic_duplicate_key_is_rejected_at_runtime(self) -> None:
        program = compile_program(
            'fn main() { let a = "x" let b = "x" let values = {a: 1, b: 2} }'
        )
        with self.assertRaisesRegex(KoscheiRuntimeError, "KS3101"):
            Interpreter(program, []).execute_main()


class MapToolingTests(unittest.TestCase):
    SOURCE = (
        "fn main() {\n"
        '    let customer = {"name":"Ali","age":42}\n'
        '    let updated = customer.set("city","Istanbul")\n'
        "    println(updated.keys())\n"
        "}\n"
    )

    def test_formatter_is_idempotent_and_preserves_tokens(self) -> None:
        formatted = format_source(self.SOURCE)
        self.assertEqual(formatted, format_source(formatted))
        self.assertEqual(
            [(token.type, token.value) for token in tokenize(self.SOURCE)],
            [(token.type, token.value) for token in tokenize(formatted)],
        )
        self.assertIn('let customer = { "name": "Ali", "age": 42 }', formatted)

    def test_empty_map_does_not_swallow_block_closing_brace(self) -> None:
        formatted = format_source("fn main(){let values={}}")
        self.assertEqual(
            formatted,
            "fn main() {\n"
            "    let values = {}\n"
            "}\n",
        )

    def test_native_backend_generates_map_runtime(self) -> None:
        generated = generate_go(
            compile_program(
                'fn main() { let values = {"x": 1} '
                'let x = values.get("x") or 0 println(x) }'
            )
        )
        self.assertIn("ksNewMap", generated)
        self.assertIn("ksMapGet", generated)

    def test_capability_manifest_walks_map_entries(self) -> None:
        program = parse(
            "fn main(caps: SystemCaps) { "
            'let grants = {"api": caps.net.allow("https://example.com")} '
            "}"
        )
        manifest = analyze(program)
        self.assertEqual(manifest.grants[0].scope, "https://example.com")

    def test_explain_catalog_mentions_map_methods(self) -> None:
        diagnostic = lookup("KS1502")
        self.assertIsNotNone(diagnostic)
        self.assertIn("Map için: get, set, keys, contains", diagnostic.fix)


if __name__ == "__main__":
    unittest.main()
