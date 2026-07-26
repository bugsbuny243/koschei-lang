from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from koschei.capabilities import analyze
from koschei.diagnostics import lookup
from koschei.interpreter import Interpreter, KoscheiRuntimeError
from koschei.parser import parse
from koschei.semantic import SemanticError, check


class V07DailyProgrammingTests(unittest.TestCase):
    def run_source(self, source: str) -> str:
        program = parse(source)
        check(program)
        output = io.StringIO()
        with redirect_stdout(output):
            Interpreter(program, []).execute_main()
        return output.getvalue()

    def test_expression_interpolation_executes_calls_and_arithmetic(self) -> None:
        output = self.run_source(
            'fn main() { let items = [1, 2, 3] '
            'println("uzunluk={items.length()} toplam={1 + 2}") }'
        )
        self.assertEqual(output, "uzunluk=3 toplam=3\n")

    def test_string_trim_split_and_join(self) -> None:
        output = self.run_source(
            'fn main() { '
            'let parts = "  ali,ayşe,mehmet  ".trim().split(",") '
            'println(parts.length()) '
            'println(" | ".join(parts)) '
            '}'
        )
        self.assertEqual(output, "3\nali | ayşe | mehmet\n")

    def test_list_sort_is_immutable(self) -> None:
        output = self.run_source(
            'fn main() { let original = [3, 1, 2] let sorted = original.sort() '
            'println(original) println(sorted) }'
        )
        self.assertEqual(output, "[3, 1, 2]\n[1, 2, 3]\n")

    def test_list_filter_uses_named_bool_predicate(self) -> None:
        output = self.run_source(
            'fn positive(value: Int) -> Bool { return value > 0 } '
            'fn main() { let values = [-2, 0, 3, 1] '
            'let selected = values.filter(positive) println(selected) }'
        )
        self.assertEqual(output, "[3, 1]\n")

    def test_filter_rejects_non_bool_predicate_at_compile_time(self) -> None:
        source = (
            'fn echo(value: Int) -> Int { return value } '
            'fn main() { let values = [1] let selected = values.filter(echo) }'
        )
        with self.assertRaisesRegex(SemanticError, "Bool döndürmelidir"):
            check(parse(source))

    def test_sort_and_join_errors_remain_values(self) -> None:
        output = self.run_source(
            'fn main() { '
            'let sorted = [1, "iki"].sort() or [] '
            'let joined = ",".join(["bir", 2]) or "reddedildi" '
            'println(sorted) println(joined) '
            '}'
        )
        self.assertEqual(output, "[]\nreddedildi\n")

    def test_list_literal_cannot_launder_capability(self) -> None:
        source = (
            'fn main(caps: SystemCaps) { '
            'let net = caps.net.allow("https://api.example.com") '
            'let hidden = [net] '
            '}'
        )
        with self.assertRaisesRegex(SemanticError, "KS2401"):
            check(parse(source))

    def test_runtime_rejects_capability_list_without_semantic_check(self) -> None:
        program = parse(
            'fn main(caps: SystemCaps) { '
            'let net = caps.net.allow("https://api.example.com") '
            'let hidden = [net] '
            '}'
        )
        with self.assertRaises(KoscheiRuntimeError) as context:
            Interpreter(program, []).execute_main()
        self.assertEqual(context.exception.code, "KS3401")

    def test_explain_catalog_lists_v07_methods(self) -> None:
        diagnostic = lookup("KS1502")
        self.assertIn("trim, split, join", diagnostic.fix)
        self.assertIn("sort, filter", diagnostic.fix)

    def test_capability_manifest_walks_interpolation_expressions(self) -> None:
        program = parse(
            'fn main(caps: SystemCaps) { '
            'let net = caps.net.allow("https://api.example.com") '
            'println("cevap: {net.get(\"https://api.example.com/v1\") or \"yok\"}") '
            '}'
        )
        check(program)
        manifest = analyze(program)
        self.assertIn("net", {grant.domain for grant in manifest.grants})
        self.assertIn("get", manifest.operations["net"])


if __name__ == "__main__":
    unittest.main()
