from __future__ import annotations

import unittest

from koschei.lexer import LexerError, TokenType, tokenize


class LexerTests(unittest.TestCase):
    def test_keywords_types_symbols_and_values(self) -> None:
        source = '''
        // yorum atlanmalı
        fn main(caps: SystemCaps) {
            let mut count = 42
            let net = caps.net
            return "ok"
        }
        '''

        tokens = tokenize(source)
        token_types = [token.type for token in tokens]

        self.assertIn(TokenType.FN, token_types)
        self.assertIn(TokenType.LET, token_types)
        self.assertIn(TokenType.MUT, token_types)
        self.assertIn(TokenType.RETURN, token_types)
        self.assertIn(TokenType.TYPE, token_types)
        self.assertIn(TokenType.DOT, token_types)
        self.assertIn(TokenType.STRING, token_types)
        self.assertIn(TokenType.NUMBER, token_types)
        self.assertEqual(tokens[-1].type, TokenType.EOF)

    def test_comment_content_does_not_become_tokens(self) -> None:
        tokens = tokenize("let value = 1 // hidden_name\nreturn value")
        values = [token.value for token in tokens]
        self.assertNotIn("hidden_name", values)

    def test_unterminated_string_reports_location(self) -> None:
        with self.assertRaisesRegex(LexerError, r"satır 1, sütun 9"):
            tokenize('let x = "unfinished')

    def test_control_flow_keywords_and_bool_literals(self) -> None:
        tokens = tokenize("if true { } else { } while false { }")
        token_types = [token.type for token in tokens]

        self.assertIn(TokenType.IF, token_types)
        self.assertIn(TokenType.ELSE, token_types)
        self.assertIn(TokenType.WHILE, token_types)
        self.assertIn(TokenType.TRUE, token_types)
        self.assertIn(TokenType.FALSE, token_types)

    def test_logical_and_bang_operators(self) -> None:
        tokens = tokenize("a && b || !c")
        token_types = [token.type for token in tokens]

        self.assertIn(TokenType.AMP_AMP, token_types)
        self.assertIn(TokenType.PIPE_PIPE, token_types)
        self.assertIn(TokenType.BANG, token_types)

    def test_plain_string_stays_plain(self) -> None:
        tokens = tokenize('let s = "duz metin"')
        string_token = next(t for t in tokens if t.type is TokenType.STRING)
        self.assertEqual(string_token.value, "duz metin")

    def test_interpolated_string_produces_segments(self) -> None:
        tokens = tokenize('let s = "selam {user.email} hoş geldin"')
        token = next(t for t in tokens if t.type is TokenType.STRING_INTERP)

        self.assertEqual(
            token.value,
            (
                ("text", "selam "),
                ("expr", "user.email"),
                ("text", " hoş geldin"),
            ),
        )

    def test_escaped_braces_do_not_interpolate(self) -> None:
        tokens = tokenize(r'let s = "json: \{a\}"')
        string_token = next(t for t in tokens if t.type is TokenType.STRING)
        self.assertEqual(string_token.value, "json: {a}")

    def test_interpolation_accepts_normal_expressions(self) -> None:
        tokens = tokenize('let s = "sonuç: {1 + 2} uzunluk: {items.length()}"')
        token = next(t for t in tokens if t.type is TokenType.STRING_INTERP)
        self.assertIn(("expr", "1 + 2"), token.value)
        self.assertIn(("expr", "items.length()"), token.value)

    def test_nested_braces_inside_interpolation_are_balanced(self) -> None:
        tokens = tokenize('let s = "var: {{\"a\": 1}.contains(\"a\")}"')
        token = next(t for t in tokens if t.type is TokenType.STRING_INTERP)
        self.assertEqual(token.value, (("text", "var: "), ("expr", '{"a": 1}.contains("a")')))

    def test_empty_interpolation_is_rejected(self) -> None:
        with self.assertRaisesRegex(LexerError, "Boş interpolasyon"):
            tokenize('let s = "boş: {}"')


if __name__ == "__main__":
    unittest.main()
