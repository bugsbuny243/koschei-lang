from __future__ import annotations

import unittest

from koschei.universe_interactions_v1 import (
    UniverseInteractionError,
    applicable_interactions,
    compose_universe,
)


class UniverseInteractionsV1Tests(unittest.TestCase):
    def test_vor_nur_creates_authority_visibility_separation(self) -> None:
        plan = compose_universe(("vor", "nur"))
        self.assertIn("authority-visibility-separation", plan.interaction_ids)
        self.assertIn(
            "visibility-expansion-cannot-expand-capability",
            plan.emergent_invariants,
        )

    def test_shi_thal_binds_recovery_to_evidence(self) -> None:
        plan = compose_universe(("shi", "thal"))
        self.assertIn("evidence-bound-recovery", plan.interaction_ids)
        self.assertIn(
            "bind-recovery-commit-to-attested-effect",
            plan.emergent_obligations,
        )

    def test_ka_vor_shi_creates_authorization_provenance(self) -> None:
        plan = compose_universe(("ka", "vor", "shi"))
        self.assertIn("authority-evidence-provenance", plan.interaction_ids)
        self.assertIn("genesis-authority-seal", plan.interaction_ids)
        self.assertIn("identity-evidence-binding", plan.interaction_ids)

    def test_full_universe_adds_conservation_rule(self) -> None:
        plan = compose_universe(("ka", "vor", "shi", "thal", "nur"))
        self.assertIn("whole-universe-conservation", plan.interaction_ids)
        self.assertIn(
            "no-composition-may-create-ambient-authority",
            plan.emergent_invariants,
        )

    def test_same_input_has_stable_digest(self) -> None:
        left = compose_universe(("ka", "vor", "shi", "thal", "nur"))
        right = compose_universe(("ka", "vor", "shi", "thal", "nur"))
        self.assertEqual(left.digest, right.digest)

    def test_invalid_genesis_order_is_rejected_by_composition(self) -> None:
        with self.assertRaises(ValueError):
            compose_universe(("vor", "ka"))

    def test_empty_interaction_query_fails_closed(self) -> None:
        with self.assertRaises(UniverseInteractionError):
            applicable_interactions(())


if __name__ == "__main__":
    unittest.main()
