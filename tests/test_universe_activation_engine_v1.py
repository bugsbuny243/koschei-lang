from __future__ import annotations

import unittest

from koschei.universe_activation_engine_v1 import compile_activation_plan


class UniverseActivationEngineTests(unittest.TestCase):
    def test_full_universe_has_terminal_conservation_seal(self) -> None:
        plan = compile_activation_plan(("ka", "vor", "shi", "thal", "nur"))
        self.assertEqual(plan.steps[-1].phase, "conservation")
        self.assertEqual(
            plan.steps[-1].obligation,
            "seal-whole-universe-conservation-proof",
        )

    def test_activation_is_deterministic(self) -> None:
        first = compile_activation_plan(("ka", "vor", "shi"))
        second = compile_activation_plan(("ka", "vor", "shi"))
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(first.steps, second.steps)

    def test_later_phases_depend_on_prior_active_phase(self) -> None:
        plan = compile_activation_plan(("ka", "vor", "shi"))
        genesis_ids = {step.step_id for step in plan.steps if step.phase == "genesis"}
        authority_steps = [step for step in plan.steps if step.phase == "authority"]
        evidence_steps = [step for step in plan.steps if step.phase == "evidence"]
        self.assertTrue(authority_steps)
        self.assertTrue(evidence_steps)
        self.assertTrue(any(genesis_ids.intersection(step.requires) for step in authority_steps))
        authority_ids = {step.step_id for step in authority_steps}
        self.assertTrue(any(authority_ids.intersection(step.requires) for step in evidence_steps))

    def test_vor_nur_keeps_authority_before_visibility(self) -> None:
        plan = compile_activation_plan(("vor", "nur"))
        phases = [step.phase for step in plan.steps]
        self.assertLess(phases.index("authority"), phases.index("visibility"))


if __name__ == "__main__":
    unittest.main()
