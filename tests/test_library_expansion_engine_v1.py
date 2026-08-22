from __future__ import annotations

import unittest

from koschei.library_expansion_engine_v1 import (
    LIBRARY_BINDINGS,
    compile_library_expansion,
)


class LibraryExpansionEngineTests(unittest.TestCase):
    def test_full_universe_expands_every_activation_obligation(self) -> None:
        plan = compile_library_expansion(("ka", "vor", "shi", "thal", "nur"))
        self.assertTrue(plan.steps)
        self.assertEqual(plan.sigils, ("ka", "vor", "shi", "thal", "nur"))
        self.assertTrue(all(step.obligation in LIBRARY_BINDINGS for step in plan.steps))
        self.assertEqual(
            plan.steps[-1].obligation,
            "seal-whole-universe-conservation-proof",
        )

    def test_only_least_authority_binding_may_grant_authority(self) -> None:
        authority = [
            binding.obligation
            for binding in LIBRARY_BINDINGS.values()
            if binding.grants_authority
        ]
        self.assertEqual(authority, ["derive-least-authority"])

    def test_vor_nur_keeps_authority_and_visibility_separate(self) -> None:
        plan = compile_library_expansion(("vor", "nur"))
        obligations = {step.obligation for step in plan.steps}
        self.assertIn("derive-least-authority", obligations)
        self.assertIn("evaluate-authority-and-visibility-independently", obligations)
        self.assertIn("shrink-visibility-envelope", obligations)

    def test_expansion_is_deterministic(self) -> None:
        left = compile_library_expansion(("ka", "vor", "shi"))
        right = compile_library_expansion(("ka", "vor", "shi"))
        self.assertEqual(left.digest, right.digest)
        self.assertEqual(left.steps, right.steps)


if __name__ == "__main__":
    unittest.main()
