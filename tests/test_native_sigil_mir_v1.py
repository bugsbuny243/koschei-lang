from dataclasses import replace
import unittest

from koschei.native_sigil_mir_v1 import NativeSigilMirError, lower_native_sigils
from koschei.parser import parse


class NativeSigilMirTests(unittest.TestCase):
    def test_real_source_lowers_to_sealed_native_mir(self) -> None:
        program = parse(
            "ka treasury;\n"
            "vor withdrawal;\n"
            "shi evidence;\n"
            "thal recovery;\n"
            "nur visibility;\n"
        )
        mir = lower_native_sigils(program)
        mir.assert_sealed()
        self.assertEqual(
            tuple(item.sigil for item in mir.bindings),
            ("ka", "vor", "shi", "thal", "nur"),
        )
        self.assertEqual(mir.bindings[1].semantic_domain, "authority.narrowing.effects")
        self.assertTrue(mir.bindings[1].may_grant_authority)
        self.assertFalse(mir.bindings[0].may_grant_authority)

    def test_lowering_is_deterministic(self) -> None:
        source = "ka treasury;\nvor withdrawal;\nshi evidence;\n"
        left = lower_native_sigils(parse(source))
        right = lower_native_sigils(parse(source))
        self.assertEqual(left.fingerprint, right.fingerprint)
        self.assertEqual(left.universe_plan_digest, right.universe_plan_digest)

    def test_subject_is_part_of_seal(self) -> None:
        left = lower_native_sigils(parse("ka treasury;\nvor withdrawal;\n"))
        right = lower_native_sigils(parse("ka treasury;\nvor signing;\n"))
        self.assertNotEqual(left.fingerprint, right.fingerprint)

    def test_tamper_fails_closed(self) -> None:
        mir = lower_native_sigils(parse("ka treasury;\nvor withdrawal;\n"))
        tampered_binding = replace(mir.bindings[1], subject="root")
        tampered = replace(mir, bindings=(mir.bindings[0], tampered_binding))
        with self.assertRaises(NativeSigilMirError):
            tampered.assert_sealed()


if __name__ == "__main__":
    unittest.main()
