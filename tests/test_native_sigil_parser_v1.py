from __future__ import annotations

import unittest

from koschei.native_sigil_parser_v1 import (
    NativeSigilParserError,
    parse_native_sigils,
)


class NativeSigilParserTests(unittest.TestCase):
    def test_parses_full_five_sigil_surface(self) -> None:
        program = parse_native_sigils(
            "ka treasury; vor withdrawal; shi proof; thal recovery; nur view;"
        )
        self.assertEqual(program.sigils, ("ka", "vor", "shi", "thal", "nur"))
        self.assertEqual(
            tuple(item.subject for item in program.declarations),
            ("treasury", "withdrawal", "proof", "recovery", "view"),
        )

    def test_requires_explicit_subject(self) -> None:
        with self.assertRaises(NativeSigilParserError):
            parse_native_sigils("ka;")

    def test_requires_explicit_terminator(self) -> None:
        with self.assertRaises(NativeSigilParserError):
            parse_native_sigils("ka treasury")

    def test_rejects_legacy_function_surface_in_native_slice(self) -> None:
        with self.assertRaises(NativeSigilParserError):
            parse_native_sigils("fn main() {}")


if __name__ == "__main__":
    unittest.main()
