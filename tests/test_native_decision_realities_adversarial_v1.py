from __future__ import annotations

import itertools
import unittest

from koschei.native_decision_realities_v1 import (
    NativeDecisionRealityError,
    check_native_decision_reality,
)


class NativeDecisionRealitiesAdversarialV1Tests(unittest.TestCase):
    def test_settle_arity_is_exact(self) -> None:
        for term in (
            "settle gate left",
            "settle gate left right extra",
        ):
            with self.subTest(term=term):
                with self.assertRaisesRegex(NativeDecisionRealityError, "settle requires exactly"):
                    check_native_decision_reality(
                        "witness gate truth yes\n"
                        "witness left 1\n"
                        "witness right 2\n"
                        f"witness result {term}\n"
                        "resolve result\n"
                    )

    def test_settle_and_mainstream_control_words_are_reserved_from_identity(self) -> None:
        for word in ("settle", "if", "else", "match", "case", "switch", "select"):
            with self.subTest(word=word):
                with self.assertRaises(NativeDecisionRealityError):
                    check_native_decision_reality(
                        f"witness {word} 1\n"
                        f"resolve {word}\n"
                    )

    def test_legacy_control_clause_shapes_have_no_decision_fallback(self) -> None:
        for source in (
            "if gate\nresolve gate\n",
            "else gate\nresolve gate\n",
            "match gate\nresolve gate\n",
            "case gate\nresolve gate\n",
            "switch gate\nresolve gate\n",
            "select gate\nresolve gate\n",
            "witness gate truth yes\nwitness result if gate 1 2\nresolve result\n",
            "witness gate truth yes\nwitness result gate ? 1 : 2\nresolve result\n",
        ):
            with self.subTest(source=source):
                with self.assertRaises(NativeDecisionRealityError):
                    check_native_decision_reality(source)

    def test_unselected_glyph_overflow_is_statically_rejected(self) -> None:
        seed = "a" * 65536
        source = (
            "witness gate truth yes\n"
            "witness good glyphs 2 ok\n"
            f"witness seed glyphs 65536 {seed}\n"
            "witness d1 merge seed seed\n"
            "witness d2 merge d1 d1\n"
            "witness d3 merge d2 d2\n"
            "witness d4 merge d3 d3\n"
            "witness bad merge d4 d4\n"
            "witness result settle gate good bad\n"
            "resolve result\n"
        )
        with self.assertRaisesRegex(NativeDecisionRealityError, "exceeds result byte budget"):
            check_native_decision_reality(source)

    def test_cycle_in_unselected_candidate_is_rejected_structurally(self) -> None:
        with self.assertRaisesRegex(NativeDecisionRealityError, "cycle"):
            check_native_decision_reality(
                "witness gate truth yes\n"
                "witness good 42\n"
                "witness b sum c 1\n"
                "witness c sum b 1\n"
                "witness result settle gate good b\n"
                "resolve result\n"
            )

    def test_inactive_candidate_needed_by_other_active_edge_remains_active(self) -> None:
        checked = check_native_decision_reality(
            "witness gate truth yes\n"
            "witness good 40\n"
            "witness other 2\n"
            "witness pick settle gate good other\n"
            "witness result sum pick other\n"
            "resolve result\n"
        )
        self.assertEqual(checked.value.value, 42)
        self.assertIn("other", checked.active_order)

    def test_nested_settle_tracks_only_selected_candidate_paths(self) -> None:
        checked = check_native_decision_reality(
            "witness innergate truth no\n"
            "witness outergate truth yes\n"
            "witness innerpositive 10\n"
            "witness innernegative 40\n"
            "witness inner settle innergate innerpositive innernegative\n"
            "witness outernegative 7\n"
            "witness result settle outergate inner outernegative\n"
            "resolve result\n"
        )
        self.assertEqual(checked.value.value, 40)
        self.assertIn("innergate", checked.active_order)
        self.assertIn("outergate", checked.active_order)
        self.assertIn("innernegative", checked.active_order)
        self.assertNotIn("innerpositive", checked.active_order)
        self.assertNotIn("outernegative", checked.active_order)

    def test_witness_permutations_do_not_change_decision_reality(self) -> None:
        clauses = (
            "witness gate truth yes",
            "witness chosen 42",
            "witness rejected 7",
            "witness result settle gate chosen rejected",
        )
        baseline = check_native_decision_reality("\n".join(clauses) + "\nresolve result\n")
        for permutation in itertools.permutations(clauses):
            checked = check_native_decision_reality("\n".join(permutation) + "\nresolve result\n")
            self.assertEqual(checked.value, baseline.value)
            self.assertEqual(checked.structural_order, baseline.structural_order)
            self.assertEqual(checked.active_order, baseline.active_order)


if __name__ == "__main__":
    unittest.main()
