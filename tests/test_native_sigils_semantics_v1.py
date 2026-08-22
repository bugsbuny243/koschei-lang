from __future__ import annotations

import unittest

from koschei.native_sigil_semantics_v1 import (
    NativeSigilSemanticError,
    check_native_sigils,
)
from koschei.parser import parse


class NativeSigilSemanticTests(unittest.TestCase):
    def test_real_source_parses_and_binds_all_five_sigils(self) -> None:
        program = parse(
            """
            ka treasury;
            vor withdrawal;
            shi evidence;
            thal recovery;
            nur visibility;
            """
        )
        typed = check_native_sigils(program)
        self.assertEqual(
            tuple(item.sigil for item in typed.declarations),
            ("ka", "vor", "shi", "thal", "nur"),
        )
        self.assertEqual(typed.declarations[0].semantic_domain, "genesis.identity.integrity")
        self.assertEqual(typed.declarations[1].semantic_domain, "authority.narrowing.effects")
        self.assertTrue(typed.declarations[1].may_grant_authority)
        self.assertTrue(all(item.fail_closed for item in typed.declarations))
        self.assertTrue(typed.universe_plan_digest)
        self.assertTrue(typed.digest)

    def test_ka_must_be_first_when_composed(self) -> None:
        program = parse("vor withdrawal; ka treasury;")
        with self.assertRaisesRegex(NativeSigilSemanticError, "ka is the genesis boundary"):
            check_native_sigils(program)

    def test_duplicate_sigil_is_rejected_by_universe_semantics(self) -> None:
        program = parse("ka treasury; ka identity;")
        with self.assertRaisesRegex(NativeSigilSemanticError, "duplicate sigils"):
            check_native_sigils(program)

    def test_digest_is_deterministic(self) -> None:
        source = "ka treasury; vor withdrawal; shi evidence;"
        first = check_native_sigils(parse(source))
        second = check_native_sigils(parse(source))
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(first.universe_plan_digest, second.universe_plan_digest)


if __name__ == "__main__":
    unittest.main()
