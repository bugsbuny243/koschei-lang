from __future__ import annotations

import unittest

from koschei.native_sigil_semantics_v1 import (
    NativeSigilSemanticError,
    check_native_sigils,
)
from koschei.parser import parse


class NativeSigilSemanticTests(unittest.TestCase):
    def test_real_source_parses_and_binds_all_five_sigils_to_one_admitted_subject(self) -> None:
        program = parse(
            """
            ka treasury;
            vor treasury;
            shi treasury;
            thal treasury;
            nur treasury;
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
        program = parse("vor treasury; ka treasury;")
        with self.assertRaisesRegex(NativeSigilSemanticError, "ka is the genesis boundary"):
            check_native_sigils(program)

    def test_duplicate_sigil_is_rejected_by_universe_semantics(self) -> None:
        program = parse("ka treasury; ka treasury;")
        with self.assertRaises(NativeSigilSemanticError):
            check_native_sigils(program)

    def test_vor_without_genesis_admission_is_rejected(self) -> None:
        program = parse("vor BuHicVarOlmayanSey;")
        with self.assertRaisesRegex(
            NativeSigilSemanticError,
            "has no preceding ka admission",
        ):
            check_native_sigils(program)

    def test_non_genesis_roots_cannot_invent_subjects(self) -> None:
        for sigil in ("vor", "shi", "thal", "nur"):
            with self.subTest(sigil=sigil):
                program = parse(f"ka treasury; {sigil} invented;")
                with self.assertRaisesRegex(
                    NativeSigilSemanticError,
                    "has no preceding ka admission",
                ):
                    check_native_sigils(program)

    def test_digest_is_deterministic(self) -> None:
        source = "ka treasury; vor treasury; shi treasury;"
        first = check_native_sigils(parse(source))
        second = check_native_sigils(parse(source))
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(first.universe_plan_digest, second.universe_plan_digest)


if __name__ == "__main__":
    unittest.main()
