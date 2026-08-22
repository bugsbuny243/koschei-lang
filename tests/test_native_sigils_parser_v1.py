from __future__ import annotations

import unittest

from koschei.native_sigils_v1 import NativeProgram
from koschei.parser import ParserError, parse


class NativeSigilParserTests(unittest.TestCase):
    def test_parses_native_sigils_into_program_surface(self) -> None:
        program = parse(
            """
            ka treasury;
            vor withdrawal;
            shi settlement;
            thal recovery;
            nur visibility;
            """
        )
        self.assertIsInstance(program, NativeProgram)
        self.assertEqual(
            [(item.sigil, item.subject) for item in program.sigils],
            [
                ("ka", "treasury"),
                ("vor", "withdrawal"),
                ("shi", "settlement"),
                ("thal", "recovery"),
                ("nur", "visibility"),
            ],
        )

    def test_sigils_can_coexist_with_legacy_function_surface(self) -> None:
        program = parse(
            """
            ka treasury
            fn main() { return }
            """
        )
        self.assertEqual(len(program.sigils), 1)
        self.assertEqual(program.sigils[0].subject, "treasury")
        self.assertEqual(len(program.declarations), 1)
        self.assertEqual(program.declarations[0].name, "main")

    def test_sigil_requires_explicit_subject(self) -> None:
        with self.assertRaises(ParserError):
            parse("ka;")

    def test_capitalized_subject_is_allowed_as_canonical_name(self) -> None:
        program = parse("ka Treasury;")
        self.assertEqual(program.sigils[0].subject, "Treasury")


if __name__ == "__main__":
    unittest.main()
