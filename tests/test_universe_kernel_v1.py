from __future__ import annotations

import unittest

from koschei.universe_kernel_v1 import (
    SIGILS,
    UniverseKernelError,
    compile_universe_plan,
)


class UniverseKernelTests(unittest.TestCase):
    def test_full_universe_expands_to_deep_system_plan(self) -> None:
        plan = compile_universe_plan(("ka", "vor", "shi", "thal", "nur"))
        self.assertEqual(plan.sigils, ("ka", "vor", "shi", "thal", "nur"))
        self.assertIn("koschei.runtime_boot_v1", plan.activated_modules)
        self.assertIn(
            "koschei.library_adversary_learning_resistance_v0",
            plan.activated_modules,
        )
        self.assertIn("commit-or-abort-recovery", plan.obligations)
        self.assertEqual(len(plan.digest), 64)

    def test_same_sequence_has_same_digest(self) -> None:
        left = compile_universe_plan(("ka", "vor", "nur"))
        right = compile_universe_plan(("ka", "vor", "nur"))
        self.assertEqual(left.digest, right.digest)

    def test_order_is_semantic_and_changes_digest(self) -> None:
        left = compile_universe_plan(("vor", "shi"))
        right = compile_universe_plan(("shi", "vor"))
        self.assertNotEqual(left.digest, right.digest)

    def test_ka_must_be_first_when_composed(self) -> None:
        with self.assertRaises(UniverseKernelError):
            compile_universe_plan(("vor", "ka"))

    def test_duplicate_sigil_is_rejected(self) -> None:
        with self.assertRaises(UniverseKernelError):
            compile_universe_plan(("ka", "vor", "vor"))

    def test_unknown_sigil_is_rejected(self) -> None:
        with self.assertRaises(UniverseKernelError):
            compile_universe_plan(("ka", "javascript"))

    def test_only_vor_may_grant_authority(self) -> None:
        granting = {name for name, spec in SIGILS.items() if spec.may_grant_authority}
        self.assertEqual(granting, {"vor"})

    def test_every_sigil_is_fail_closed(self) -> None:
        self.assertTrue(all(spec.fail_closed for spec in SIGILS.values()))


if __name__ == "__main__":
    unittest.main()
