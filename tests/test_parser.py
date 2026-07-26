from __future__ import annotations

import unittest

from koschei.ast_nodes import (
    BinaryExpression,
    IfStatement,
    InterpolatedString,
    BinaryExpression,
    CallExpression,
    LetStatement,
    Literal,
    OrBlockExpression,
    OrElseExpression,
    OrReturnExpression,
    ReturnStatement,
    UnaryExpression,
    WhileStatement,
)
from koschei.parser import ParserError, parse


SAMPLE = '''
fn fetch_data(net: NetCaps, url: String) -> String or Error {
    let response = net.get(url) or return Error("Veri alınamadı")
    return response.text()
}

fn main(caps: SystemCaps) {
    let allowed_net = caps.net.allow("https://api.example.com")
    let mut retry_count = 3
    return
}
'''


class ParserTests(unittest.TestCase):
    def test_parses_functions_parameters_and_union_return_type(self) -> None:
        program = parse(SAMPLE)

        self.assertEqual(len(program.declarations), 2)
        fetch_data = program.declarations[0]
        self.assertEqual(fetch_data.name, "fetch_data")
        self.assertEqual([item.name for item in fetch_data.parameters], ["net", "url"])
        self.assertEqual(str(fetch_data.return_type), "String or Error")

    def test_parses_or_return_and_mutability_metadata(self) -> None:
        program = parse(SAMPLE)
        fetch_data, main = program.declarations

        response = fetch_data.body.statements[0]
        self.assertIsInstance(response, LetStatement)
        self.assertFalse(response.is_mutable)
        self.assertIsInstance(response.value, OrReturnExpression)

        retry_count = main.body.statements[1]
        self.assertIsInstance(retry_count, LetStatement)
        self.assertTrue(retry_count.is_mutable)
        self.assertIsInstance(main.body.statements[-1], ReturnStatement)

    def test_reports_missing_closing_brace(self) -> None:
        with self.assertRaisesRegex(ParserError, "Blok sonunda"):
            parse("fn main() { let value = 1")

    # ------------------------------------------------------------------
    # Operatörler ve öncelik
    # ------------------------------------------------------------------

    def test_binary_operator_precedence(self) -> None:
        program = parse("fn main() { let x = 1 + 2 * 3 }")
        let = program.declarations[0].body.statements[0]
        assert isinstance(let, LetStatement)
        expr = let.value

        # 1 + (2 * 3) olarak ağaçlanmalı
        self.assertIsInstance(expr, BinaryExpression)
        self.assertEqual(expr.operator, "+")
        self.assertIsInstance(expr.right, BinaryExpression)
        self.assertEqual(expr.right.operator, "*")

    def test_comparison_and_logical_operators(self) -> None:
        program = parse("fn main() { let ok = 1 < 2 && 3 != 4 || !false }")
        let = program.declarations[0].body.statements[0]
        assert isinstance(let, LetStatement)
        expr = let.value

        self.assertIsInstance(expr, BinaryExpression)
        self.assertEqual(expr.operator, "||")
        self.assertIsInstance(expr.right, UnaryExpression)
        self.assertEqual(expr.right.operator, "!")

    def test_unary_minus(self) -> None:
        program = parse("fn main() { let x = -5 + 3 }")
        let = program.declarations[0].body.statements[0]
        assert isinstance(let, LetStatement)
        self.assertIsInstance(let.value, BinaryExpression)
        self.assertIsInstance(let.value.left, UnaryExpression)

    # ------------------------------------------------------------------
    # Kontrol akışı
    # ------------------------------------------------------------------

    def test_if_else_if_else_chain(self) -> None:
        program = parse(
            "fn main() { "
            "if true { return } "
            "else if false { return } "
            "else { return } "
            "}"
        )
        statement = program.declarations[0].body.statements[0]
        self.assertIsInstance(statement, IfStatement)
        self.assertIsInstance(statement.else_branch, IfStatement)
        self.assertIsNotNone(statement.else_branch.else_branch)

    def test_while_statement(self) -> None:
        program = parse("fn main() { while true { return } }")
        statement = program.declarations[0].body.statements[0]
        self.assertIsInstance(statement, WhileStatement)

    # ------------------------------------------------------------------
    # 'or' biçimleri
    # ------------------------------------------------------------------

    def test_or_default_expression(self) -> None:
        program = parse('fn main() { let port = read() or 8080 }')
        let = program.declarations[0].body.statements[0]
        assert isinstance(let, LetStatement)
        self.assertIsInstance(let.value, OrElseExpression)
        self.assertIsInstance(let.value.fallback, Literal)

    def test_or_block_expression(self) -> None:
        program = parse('fn main() { let port = read() or { println("x") } }')
        let = program.declarations[0].body.statements[0]
        assert isinstance(let, LetStatement)
        self.assertIsInstance(let.value, OrBlockExpression)

    def test_bare_or_return_before_next_statement(self) -> None:
        program = parse(
            "fn main() { let a = read() or return let b = 2 }"
        )
        statements = program.declarations[0].body.statements
        self.assertEqual(len(statements), 2)
        first = statements[0]
        assert isinstance(first, LetStatement)
        self.assertIsInstance(first.value, OrReturnExpression)
        self.assertIsNone(first.value.error)

    # ------------------------------------------------------------------
    # String interpolasyonu
    # ------------------------------------------------------------------

    def test_interpolated_string_builds_member_chain(self) -> None:
        program = parse('fn main(user: String) { println("selam {user}") }')
        statement = program.declarations[0].body.statements[0]
        call = statement.expression
        argument = call.arguments[0]
        self.assertIsInstance(argument, InterpolatedString)
        self.assertEqual(len(argument.parts), 2)  # "selam " + user

    def test_interpolated_string_parses_calls_and_arithmetic(self) -> None:
        program = parse(
            'fn main() { let items = [1, 2] println("{items.length()}:{1 + 2}") }'
        )
        statement = program.declarations[0].body.statements[1]
        argument = statement.expression.arguments[0]
        self.assertIsInstance(argument, InterpolatedString)
        self.assertIsInstance(argument.parts[0], CallExpression)
        self.assertIsInstance(argument.parts[2], BinaryExpression)

    def test_invalid_interpolation_expression_is_parser_error(self) -> None:
        with self.assertRaisesRegex(ParserError, "Geçersiz interpolasyon"):
            parse('fn main() { println("bozuk: {1 + }") }')


if __name__ == "__main__":
    unittest.main()
