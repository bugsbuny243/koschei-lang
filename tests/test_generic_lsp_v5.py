from __future__ import annotations

import unittest

from koschei.lsp_v5 import diagnostics_for_source


class GenericLspParityTests(unittest.TestCase):
    def test_valid_generic_function_has_no_live_diagnostic(self) -> None:
        source = """
fn identity<T>(value: T) -> T { return value }
fn main() { let answer = identity(42) println(answer + 1) }
"""
        self.assertEqual(diagnostics_for_source(source), [])

    def test_conflicting_generic_evidence_is_live_ks1307(self) -> None:
        source = """
fn same<T>(left: T, right: T) -> T { return left }
fn main() { println(same(1, "two")) }
"""
        diagnostics = diagnostics_for_source(source)
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0]["code"], "KS1307")


if __name__ == "__main__":
    unittest.main()
