from dataclasses import replace
import unittest

from koschei.native_sigil_mir_v1 import NativeSigilMirError, lower_native_sigils
from koschei.native_sigil_semantics_v1 import check_native_sigils
from koschei.parser import parse


class NativeSigilMirTests(unittest.TestCase):
    def test_real_source_lowers_to_sealed_native_mir(self) -> None:
        program = parse(
            "ka treasury;\n"
            "vor treasury;\n"
            "shi treasury;\n"
            "thal treasury;\n"
            "nur treasury;\n"
        )
        mir = lower_native_sigils(program)
        mir.assert_sealed()
        self.assertEqual(
            tuple(item.sigil for item in mir.bindings),
            ("ka", "vor", "shi", "thal", "nur"),
        )
        self.assertTrue(all(item.subject == "treasury" for item in mir.bindings))
        self.assertEqual(mir.bindings[1].semantic_domain, "authority.narrowing.effects")
        self.assertTrue(mir.bindings[1].may_grant_authority)
        self.assertFalse(mir.bindings[0].may_grant_authority)
        self.assertFalse(any(item.may_grant_authority for item in mir.bindings[2:]))

    def test_lowering_is_deterministic(self) -> None:
        source = "ka treasury;\nvor treasury;\nshi treasury;\n"
        left = lower_native_sigils(parse(source))
        right = lower_native_sigils(parse(source))
        self.assertEqual(left.fingerprint, right.fingerprint)
        self.assertEqual(left.universe_plan_digest, right.universe_plan_digest)

    def test_subject_is_part_of_seal(self) -> None:
        left = lower_native_sigils(parse("ka treasury;\nvor treasury;\n"))
        right = lower_native_sigils(parse("ka signing;\nvor signing;\n"))
        self.assertNotEqual(left.fingerprint, right.fingerprint)

    def test_source_location_is_diagnostic_not_semantic_identity(self) -> None:
        left = lower_native_sigils(parse("ka treasury;\nvor treasury;\n"))
        right = lower_native_sigils(parse("\nka treasury;\nvor treasury;\n"))
        self.assertNotEqual(
            (left.bindings[0].source_line, left.bindings[1].source_line),
            (right.bindings[0].source_line, right.bindings[1].source_line),
        )
        self.assertEqual(left.fingerprint, right.fingerprint)
        self.assertEqual(left.universe_plan_digest, right.universe_plan_digest)

    def test_tamper_fails_closed(self) -> None:
        mir = lower_native_sigils(parse("ka treasury;\nvor treasury;\n"))
        tampered_binding = replace(mir.bindings[1], subject="root")
        tampered = replace(mir, bindings=(mir.bindings[0], tampered_binding))
        with self.assertRaises(NativeSigilMirError):
            tampered.assert_sealed()

    def test_foreign_semantic_report_is_rejected(self) -> None:
        program = parse("ka treasury;\nvor treasury;\n")
        foreign = check_native_sigils(parse("ka signing;\nvor signing;\n"))
        with self.assertRaisesRegex(NativeSigilMirError, "does not match"):
            lower_native_sigils(program, foreign)

    def test_tampered_semantic_report_is_rejected(self) -> None:
        program = parse("ka treasury;\nvor treasury;\n")
        semantic = check_native_sigils(program)
        tampered_declaration = replace(
            semantic.declarations[1],
            may_grant_authority=False,
        )
        tampered = replace(
            semantic,
            declarations=(semantic.declarations[0], tampered_declaration),
        )
        with self.assertRaisesRegex(NativeSigilMirError, "does not match"):
            lower_native_sigils(program, tampered)


if __name__ == "__main__":
    unittest.main()
