from __future__ import annotations

import unittest

from koschei.lexer import TokenType, tokenize


class NativeSigilLexerTests(unittest.TestCase):
    def test_five_native_sigils_are_reserved_language_tokens(self) -> None:
        tokens = tokenize("ka treasury; vor withdrawal; shi proof; thal recovery; nur view;")
        types = [token.type for token in tokens]
        self.assertEqual(
            types,
            [
                TokenType.KA,
                TokenType.IDENTIFIER,
                TokenType.SEMICOLON,
                TokenType.VOR,
                TokenType.IDENTIFIER,
                TokenType.SEMICOLON,
                TokenType.SHI,
                TokenType.IDENTIFIER,
                TokenType.SEMICOLON,
                TokenType.THAL,
                TokenType.IDENTIFIER,
                TokenType.SEMICOLON,
                TokenType.NUR,
                TokenType.IDENTIFIER,
                TokenType.SEMICOLON,
                TokenType.EOF,
            ],
        )

    def test_sigils_cannot_silently_degrade_to_identifiers(self) -> None:
        expected = {
            "ka": TokenType.KA,
            "vor": TokenType.VOR,
            "shi": TokenType.SHI,
            "thal": TokenType.THAL,
            "nur": TokenType.NUR,
        }
        for source, token_type in expected.items():
            with self.subTest(source=source):
                token = tokenize(source)[0]
                self.assertIs(token.type, token_type)
                self.assertEqual(token.value, source)

    def test_similar_names_remain_ordinary_identifiers(self) -> None:
        tokens = tokenize("kale vortex shiver thalia nurse")
        self.assertTrue(all(token.type is TokenType.IDENTIFIER for token in tokens[:-1]))


if __name__ == "__main__":
    unittest.main()
