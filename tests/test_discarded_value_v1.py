"""KS1402: a value method's result written alone is refused; KS1502 for unknown String methods."""
from __future__ import annotations

import unittest

from koschei.parser import parse
from koschei.semantic import SemanticError, check


def compile_program(source: str):
    program = parse(source)
    check(program)
    return program


class DiscardedValueTests(unittest.TestCase):
    def refused(self, source: str, code: str) -> None:
        with self.assertRaisesRegex(SemanticError, code):
            compile_program(source)

    def test_discarded_push_is_refused(self) -> None:
        self.refused("fn main() {\n    let mut items = [1]\n    items.push(2)\n}\n", "KS1402")

    def test_discarded_push_inside_a_loop_is_refused(self) -> None:
        self.refused(
            "fn main() {\n    let mut items = [1]\n    for x in [2, 3] {\n        items.push(x)\n    }\n}\n",
            "KS1402",
        )

    def test_discarded_map_set_and_string_methods_are_refused(self) -> None:
        self.refused('fn main() {\n    let m = {"a": 1}\n    m.set("b", 2)\n}\n', "KS1402")
        self.refused('fn main() {\n    let t = " x "\n    t.trim()\n}\n', "KS1402")

    def test_used_results_compile(self) -> None:
        compile_program(
            "fn main() {\n    let mut items = [1]\n    items = items.push(2)\n"
            "    let more = items.push(3)\n    println(more.length())\n}\n"
        )

    def test_function_calls_as_statements_still_compile(self) -> None:
        compile_program(
            "fn shout(text: String) {\n    println(text)\n}\n\nfn main() {\n    shout(\"hi\")\n}\n"
        )

    def test_fallible_discard_keeps_its_own_code(self) -> None:
        self.refused('fn main() {\n    let values = {}\n    values.get("name")\n}\n', "KS1401")

    def test_unknown_string_method_is_reported_as_unknown(self) -> None:
        with self.assertRaises(SemanticError) as caught:
            compile_program('fn main() {\n    let raw = "ab".bytes()\n}\n')
        self.assertEqual(caught.exception.code, "KS1502")
        self.assertIn("to_bytes", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
