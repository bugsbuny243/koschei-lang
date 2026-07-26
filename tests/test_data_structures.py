from __future__ import annotations

import io
import pathlib
import unittest
from contextlib import redirect_stdout

from koschei.codegen_go import CodegenError, generate_go
from koschei.formatter import format_source
from koschei.interpreter import Interpreter, StructValue
from koschei.lexer import tokenize
from koschei.parser import ParserError, parse
from koschei.semantic import SemanticError, check

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


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


class StructParsingTests(unittest.TestCase):
    def test_struct_declaration_is_parsed(self) -> None:
        program = parse("struct User { id: Int, name: String }\nfn main() { return }")
        self.assertEqual(len(program.structs), 1)
        self.assertEqual(program.structs[0].name, "User")
        self.assertEqual(
            [field.name for field in program.structs[0].fields], ["id", "name"]
        )

    def test_struct_name_must_be_a_type_name(self) -> None:
        with self.assertRaisesRegex(ParserError, "büyük harfle"):
            parse("struct user { id: Int }")

    def test_trailing_commas_are_allowed(self) -> None:
        program = parse(
            "struct User { id: Int, name: String, }\n"
            'fn main() { let items = [1, 2, 3, ] let u = User { id: 1, name: "o", } }'
        )
        self.assertEqual(len(program.structs[0].fields), 2)


class StructSemanticTests(unittest.TestCase):
    def test_missing_field_is_rejected(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS1501"):
            compile_program(
                "struct User { id: Int, name: String }\n"
                "fn main() { let u = User { id: 1 } }"
            )

    def test_unknown_field_in_literal_is_rejected(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS1501"):
            compile_program(
                "struct User { id: Int }\n"
                "fn main() { let u = User { id: 1, oops: 2 } }"
            )

    def test_duplicate_field_in_declaration_is_rejected(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS1501"):
            compile_program(
                "struct User { id: Int, id: String }\nfn main() { return }"
            )

    def test_unknown_field_access_is_rejected(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS1502"):
            compile_program(
                "struct User { id: Int }\n"
                "fn main() { let u = User { id: 1 } println(u.oops) }"
            )

    def test_unknown_struct_type_is_rejected(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS1101"):
            compile_program("fn main() { let u = Missing { id: 1 } }")

    def test_field_type_is_propagated(self) -> None:
        # id alanı Int'tir; String ile toplanamaz.
        with self.assertRaisesRegex(SemanticError, "KS1301"):
            compile_program(
                "struct User { id: Int }\n"
                'fn main() { let u = User { id: 1 } let x = u.id + "a" }'
            )


class ListSemanticTests(unittest.TestCase):
    def test_list_methods_are_allowed(self) -> None:
        compile_program(
            "fn main() { "
            "let xs = [1, 2, 3] "
            "let n = xs.length() "
            "let first = xs.get(0) or 0 "
            "let more = xs.push(4) "
            "let has = xs.contains(2) "
            "}"
        )

    def test_unknown_list_method_is_rejected(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS1502"):
            compile_program("fn main() { let xs = [1] let y = xs.reverse() }")

    def test_list_get_is_not_confused_with_capability_get(self) -> None:
        # 'get' aynı zamanda bir yetki metodu adıdır; liste erişimi yetki
        # ihlali sayılmamalıdır.
        compile_program("fn main() { let xs = [1] let a = xs.get(0) or 0 }")

    def test_capability_rules_still_apply(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS2401"):
            compile_program('fn main() { let x = disk.read("/etc/passwd") or "" }')

    def test_for_requires_a_list(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS1301"):
            compile_program("fn main() { let n = 5 for x in n { println(x) } }")

    def test_loop_variable_does_not_leak(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS1101"):
            compile_program(
                "fn main() { for x in [1, 2] { println(x) } println(x) }"
            )


class RuntimeBehaviourTests(unittest.TestCase):
    def test_struct_fields_are_readable(self) -> None:
        output = run_source(
            "struct User { id: Int, name: String }\n"
            'fn main() { let u = User { id: 7, name: "onur" } println(u.name) println(u.id) }'
        )
        self.assertEqual(output, "onur\n7\n")

    def test_for_loop_iterates_in_order(self) -> None:
        output = run_source("fn main() { for x in [1, 2, 3] { println(x) } }")
        self.assertEqual(output, "1\n2\n3\n")

    def test_list_get_out_of_range_is_an_error_value(self) -> None:
        output = run_source(
            'fn main() { let xs = [1] let v = xs.get(9) or "yok" println(v) }'
        )
        self.assertEqual(output, "yok\n")

    def test_push_returns_a_new_list(self) -> None:
        output = run_source(
            "fn main() { "
            "let xs = [1] "
            "let ys = xs.push(2) "
            "let a = xs.length() "
            "let b = ys.length() "
            'println("{a} {b}") '
            "}"
        )
        self.assertEqual(output, "1 2\n")

    def test_struct_value_renders_readably(self) -> None:
        output = run_source(
            "struct User { id: Int, name: String }\n"
            'fn main() { let u = User { id: 1, name: "o" } println(u) }'
        )
        self.assertEqual(output, 'User { id: 1, name: "o" }\n')

    def test_list_renders_readably(self) -> None:
        output = run_source('fn main() { println([1, "a", true]) }')
        self.assertEqual(output, '[1, "a", true]\n')

    def test_nested_structs_in_lists(self) -> None:
        output = run_source(
            "struct Holder { address: String, percent: Int }\n"
            "fn main() { "
            'let hs = [Holder { address: "a", percent: 60 }, Holder { address: "b", percent: 5 }] '
            "let mut total = 0 "
            "for h in hs { total = total + h.percent } "
            'println("{total}") '
            "}"
        )
        self.assertEqual(output, "65\n")

    def test_struct_value_type_is_carried(self) -> None:
        program = compile_program(
            "struct User { id: Int }\nfn main() { let u = User { id: 1 } return u }"
        )
        result = Interpreter(program, []).execute_main()
        self.assertIsInstance(result, StructValue)
        self.assertEqual(result.type_name, "User")


class FormatterWithDataStructuresTests(unittest.TestCase):
    SOURCE = (
        "struct Holder {\n"
        "    address: String,\n"
        "    percent: Int,\n"
        "}\n"
        "\n"
        "fn main() {\n"
        "    let holders = [\n"
        '        Holder { address: "a", percent: 62 },\n'
        '        Holder { address: "b", percent: 24 },\n'
        "    ]\n"
        "    for h in holders {\n"
        "        println(h.address)\n"
        "    }\n"
        "}\n"
    )

    def test_struct_literals_stay_on_one_line(self) -> None:
        formatted = format_source(self.SOURCE)
        self.assertIn('Holder { address: "a", percent: 62 },', formatted)

    def test_list_contents_are_indented(self) -> None:
        formatted = format_source(self.SOURCE)
        self.assertIn('        Holder { address: "a"', formatted)
        self.assertIn("    ]", formatted)

    def test_invariants_hold(self) -> None:
        formatted = format_source(self.SOURCE)
        self.assertEqual(formatted, format_source(formatted))
        self.assertEqual(
            [(t.type, t.value) for t in tokenize(self.SOURCE)],
            [(t.type, t.value) for t in tokenize(formatted)],
        )


class NativeBackendRejectionTests(unittest.TestCase):
    """Native derleyici desteklemediği yapıyı sessizce yanlış çevirmez, reddeder."""

    def assert_ks4002(self, source: str) -> None:
        with self.assertRaises(CodegenError) as context:
            generate_go(compile_program(source))
        self.assertEqual(context.exception.code, "KS4002")

    def test_structs_are_rejected(self) -> None:
        self.assert_ks4002(
            "struct User { id: Int }\nfn main() { let u = User { id: 1 } }"
        )

    def test_lists_are_generated(self) -> None:
        generated = generate_go(compile_program("fn main() { let xs = [1, 2] println(xs) }"))
        self.assertIn("ksNewList", generated)

    def test_for_loops_are_generated(self) -> None:
        generated = generate_go(compile_program("fn main() { for x in [1] { println(x) } }"))
        self.assertIn("for _, ksv_x := range", generated)


class HoldersExampleTests(unittest.TestCase):
    def test_example_runs_and_is_canonical(self) -> None:
        path = REPO_ROOT / "examples" / "holders.ks"
        source = path.read_text(encoding="utf-8")
        self.assertEqual(source, format_source(source))
        output = run_source(source)
        self.assertIn("KRITIK", output)


if __name__ == "__main__":
    unittest.main()
