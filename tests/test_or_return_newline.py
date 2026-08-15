from __future__ import annotations

import unittest

from koschei.ast_nodes import ExpressionStatement, LetStatement, OrReturnExpression
from koschei.parser import parse


class OrReturnNewlineTests(unittest.TestCase):
    def test_bare_or_return_does_not_consume_next_line_expression_statement(self) -> None:
        program = parse(
            "fn main() {\n"
            "    let value = read() or return\n"
            '    println("next")\n'
            "}\n"
        )
        statements = program.declarations[0].body.statements
        self.assertEqual(len(statements), 2)
        first, second = statements
        self.assertIsInstance(first, LetStatement)
        self.assertIsInstance(first.value, OrReturnExpression)
        self.assertIsNone(first.value.error)
        self.assertIsInstance(second, ExpressionStatement)

    def test_or_return_explicit_error_on_same_line_is_preserved(self) -> None:
        program = parse(
            "fn main() {\n"
            '    let value = read() or return Error("failed")\n'
            "}\n"
        )
        first = program.declarations[0].body.statements[0]
        self.assertIsInstance(first, LetStatement)
        self.assertIsInstance(first.value, OrReturnExpression)
        self.assertIsNotNone(first.value.error)


if __name__ == "__main__":
    unittest.main()
