from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from koschei.ast_nodes import MatchExpression
from koschei.capabilities import analyze
from koschei.codegen_go import CodegenError, generate_go
from koschei.formatter import format_source
from koschei.interpreter import Interpreter, KoscheiRuntimeError, run
from koschei.lexer import TokenType, tokenize
from koschei.modules import check_graph, enum_declarations, load_graph, namespaces
from koschei.parser import parse
from koschei.semantic import SemanticError, check


class V08AlgebraicTypesTests(unittest.TestCase):
    def test_lexer_recognizes_enum_match_and_fat_arrow(self) -> None:
        types = [token.type for token in tokenize("enum State { Ready } match value { Ready => 1 }")]
        self.assertIn(TokenType.ENUM, types)
        self.assertIn(TokenType.MATCH, types)
        self.assertIn(TokenType.FAT_ARROW, types)

    def test_parser_supports_generic_types_and_match_ast(self) -> None:
        program = parse(
            "enum State { Empty, Ready(String), } "
            "fn inspect(value: Option<String>) -> Result<String, Error> { "
            "return match value { Some(text) => Ok(text), None => Err(Error(\"x\")), } }"
        )
        self.assertEqual(program.enums[0].name, "State")
        self.assertEqual(str(program.declarations[0].parameters[0].type_ref), "Option<String>")
        self.assertEqual(str(program.declarations[0].return_type), "Result<String, Error>")
        self.assertIsInstance(program.declarations[0].body.statements[0].value, MatchExpression)

    def test_enum_match_is_exhaustive_and_runs(self) -> None:
        source = """
        enum Status { Pending, Ready(String), Failed(Error), }
        fn describe(status: Status) -> String {
            return match status {
                Pending => "bekliyor",
                Ready(message) => message,
                Failed(error) => "hata",
            }
        }
        fn main() { println(describe(Ready("hazır"))) }
        """
        program = parse(source)
        check(program)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(run(program, []), 0)
        self.assertEqual(output.getvalue(), "hazır\n")

    def test_non_exhaustive_match_is_rejected(self) -> None:
        source = (
            "enum Status { Pending, Ready(String) } "
            "fn f(status: Status) -> String { "
            "return match status { Pending => \"x\" } }"
        )
        with self.assertRaises(SemanticError) as raised:
            check(parse(source))
        self.assertEqual(raised.exception.code, "KS1702")
        self.assertIn("Ready", raised.exception.message)

    def test_duplicate_and_unknown_match_arms_are_rejected(self) -> None:
        cases = (
            "enum S { A, B } fn f(x: S) -> Int { return match x { A => 1, A => 2, B => 3 } }",
            "enum S { A } fn f(x: S) -> Int { return match x { B => 1, A => 2 } }",
        )
        for source in cases:
            with self.subTest(source=source):
                with self.assertRaises(SemanticError) as raised:
                    check(parse(source))
                self.assertEqual(raised.exception.code, "KS1702")

    def test_variant_payload_contract_is_checked(self) -> None:
        source = "enum S { Ready(String) } fn main() { let x = Ready(1) }"
        with self.assertRaises(SemanticError) as raised:
            check(parse(source))
        self.assertEqual(raised.exception.code, "KS1301")

    def test_payload_and_binding_shape_must_match(self) -> None:
        cases = (
            "enum S { A } fn f(x: S) -> Int { return match x { A(v) => 1 } }",
            "enum S { A(Int) } fn f(x: S) -> Int { return match x { A => 1 } }",
        )
        for source in cases:
            with self.subTest(source=source):
                with self.assertRaises(SemanticError) as raised:
                    check(parse(source))
                self.assertEqual(raised.exception.code, "KS1702")

    def test_match_arm_result_types_must_unify(self) -> None:
        source = (
            "enum S { A, B } fn f(x: S) -> String { "
            "return match x { A => \"x\", B => 2 } }"
        )
        with self.assertRaises(SemanticError) as raised:
            check(parse(source))
        self.assertEqual(raised.exception.code, "KS1702")

    def test_option_and_result_are_real_generic_types(self) -> None:
        source = """
        fn maybe(active: Bool) -> Option<String> {
            if active { return Some("Onur") }
            return None()
        }
        fn result(active: Bool) -> Result<String, Error> {
            if active { return Ok("tamam") }
            return Err(Error("olmadı"))
        }
        fn main() {
            println(maybe(true) or "yok")
            println(result(false) or "hata")
        }
        """
        program = parse(source)
        check(program)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(run(program, []), 0)
        self.assertEqual(output.getvalue(), "Onur\nhata\n")

    def test_match_can_destructure_option_and_result(self) -> None:
        source = """
        fn show(value: Option<String>) -> String {
            return match value { Some(text) => text, None => "yok", }
        }
        fn status(value: Result<Int, Error>) -> String {
            return match value { Ok(number) => "ok", Err(error) => "hata", }
        }
        fn main() {
            println(show(None()))
            println(status(Err(Error("x"))))
        }
        """
        program = parse(source)
        check(program)
        output = io.StringIO()
        with redirect_stdout(output):
            run(program, [])
        self.assertEqual(output.getvalue(), "yok\nhata\n")

    def test_or_return_unwraps_result_and_propagates_err(self) -> None:
        source = """
        fn inner(ok: Bool) -> Result<String, Error> {
            if ok { return Ok("tamam") }
            return Err(Error("bozuk"))
        }
        fn outer(ok: Bool) -> Result<String, Error> {
            let value = inner(ok) or return
            return Ok(value)
        }
        fn main() {
            let result = outer(false)
            println(match result { Ok(value) => value, Err(error) => "taşındı", })
        }
        """
        program = parse(source)
        check(program)
        output = io.StringIO()
        with redirect_stdout(output):
            run(program, [])
        self.assertEqual(output.getvalue(), "taşındı\n")

    def test_mutable_assignment_keeps_inferred_type(self) -> None:
        source = 'fn main() { let mut value = 1 value = "x" }'
        with self.assertRaises(SemanticError) as raised:
            check(parse(source))
        self.assertEqual(raised.exception.code, "KS1301")

    def test_generic_arity_is_checked(self) -> None:
        cases = (
            "fn f(x: Option<String, Int>) {}",
            "fn f() -> Result<String> { return Ok(\"x\") }",
            "fn f(x: List<String>) {}",
        )
        for source in cases:
            with self.subTest(source=source):
                with self.assertRaises(SemanticError) as raised:
                    check(parse(source))
                self.assertEqual(raised.exception.code, "KS1301")

    def test_builtin_option_cannot_launder_capability(self) -> None:
        source = (
            "fn main(caps: SystemCaps) { "
            "let net = caps.net.allow(\"https://example.com\") "
            "let hidden = Some(net) }"
        )
        with self.assertRaises(SemanticError) as raised:
            check(parse(source))
        self.assertEqual(raised.exception.code, "KS2401")

    def test_legacy_union_is_narrowed_after_or_return(self) -> None:
        source = (
            "fn parse(raw: String) -> Int or Error { return raw.to_int() } "
            "fn plus_one(value: Int) -> Int { return value + 1 } "
            "fn use(raw: String) -> Int or Error { "
            "let value = parse(raw) or return Error(\"bad\") "
            "return plus_one(value) } fn main() {}"
        )
        check(parse(source))

    def test_capability_cannot_hide_in_enum_payload(self) -> None:
        source = (
            "enum Secret { Token(NetCaps) } "
            "fn main(caps: SystemCaps) { let net = caps.net.allow(\"https://example.com\") "
            "let hidden = Token(net) }"
        )
        with self.assertRaises(SemanticError) as raised:
            check(parse(source))
        self.assertEqual(raised.exception.code, "KS2402")

    def test_runtime_defensively_rejects_capability_payload(self) -> None:
        source = (
            "enum Secret { Token(NetCaps) } "
            "fn main(caps: SystemCaps) { let net = caps.net.allow(\"https://example.com\") "
            "let hidden = Token(net) }"
        )
        program = parse(source)
        with self.assertRaises(KoscheiRuntimeError) as raised:
            Interpreter(program).execute_main()
        self.assertEqual(raised.exception.code, "KS3401")

    def test_capability_manifest_walks_match_arms(self) -> None:
        source = """
        enum Choice { Safe, Fetch }
        fn main(caps: SystemCaps) {
            let choice = Fetch()
            let value = match choice {
                Safe => "x",
                Fetch => caps.net.allow("https://example.com").get("https://example.com/x") or "x",
            }
            println(value)
        }
        """
        manifest = analyze(parse(source))
        self.assertTrue(manifest.has_any)
        self.assertIn("net", manifest.operations)

    def test_formatter_is_idempotent_for_enum_match_and_generics(self) -> None:
        source = """enum State{Empty,Ready(String),}
fn show(value:Option<String>)->String{
return match value{
Some(text)=>text,
None=>"yok",
}
}
"""
        formatted = format_source(source)
        self.assertEqual(format_source(formatted), formatted)
        parse(formatted)
        self.assertIn("Option<String>", formatted)
        self.assertIn("=>", formatted)

    def test_enum_crosses_module_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "states.ks").write_text(
                "enum State { Empty, Ready(String) }\n"
                "fn make() -> State { return Ready(\"modül\") }\n",
                encoding="utf-8",
            )
            main = root / "main.ks"
            main.write_text(
                "import states\n"
                "fn show(value: State) -> String {\n"
                "    return match value { Empty => \"boş\", Ready(text) => text, }\n"
                "}\n"
                "fn main() { println(show(states.make())) }\n",
                encoding="utf-8",
            )
            graph = load_graph(main)
            check_graph(graph)
            output = io.StringIO()
            with redirect_stdout(output):
                run(
                    graph.root_module.program,
                    [],
                    namespaces=namespaces(graph),
                    imports=graph.root_module.imports,
                    enums=enum_declarations(graph),
                )
            self.assertEqual(output.getvalue(), "modül\n")

    def test_native_backend_rejects_new_v08_values_fail_closed(self) -> None:
        sources = (
            'enum S { A } fn main() { println(match A() { A => "x" }) }',
            'fn main() { let x = Some("x") println(x) }',
        )
        for source in sources:
            with self.subTest(source=source):
                with self.assertRaises(CodegenError) as raised:
                    generate_go(parse(source))
                self.assertEqual(raised.exception.code, "KS4002")


if __name__ == "__main__":
    unittest.main()
