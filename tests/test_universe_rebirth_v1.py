from __future__ import annotations

import unittest

from koschei.universe_rebirth_v1 import (
    UniverseRebirthError,
    rebirth_contained_universe,
    require_rebirth_receipt,
)
from koschei.universe_state_machine_v1 import (
    SigilState,
    contain_universe,
    initial_universe_state,
    transition_sigil,
)


class UniverseRebirthTests(unittest.TestCase):
    def _contained(self):
        state = initial_universe_state(("ka", "vor"), epoch=7)
        state = transition_sigil(state, "ka", SigilState.PREPARED, evidence_digest="ka-prep")
        state = transition_sigil(state, "ka", SigilState.SEALED, evidence_digest="ka-seal")
        state = transition_sigil(state, "ka", SigilState.ACTIVE, evidence_digest="ka-active")
        state = transition_sigil(state, "vor", SigilState.PREPARED, evidence_digest="vor-prep")
        state = transition_sigil(state, "vor", SigilState.SEALED, evidence_digest="vor-seal")
        state = transition_sigil(state, "vor", SigilState.ACTIVE, evidence_digest="vor-active")
        return contain_universe(state, evidence_digest="incident-77")

    def test_rebirth_requires_full_containment(self) -> None:
        state = initial_universe_state(("ka", "vor"))
        with self.assertRaises(UniverseRebirthError):
            rebirth_contained_universe(state, cause_evidence_digest="cause")

    def test_rebirth_moves_to_fresh_inactive_epoch(self) -> None:
        previous = self._contained()
        fresh, receipt = rebirth_contained_universe(
            previous, cause_evidence_digest="recovery-proof"
        )
        self.assertEqual(receipt.previous_epoch, 7)
        self.assertEqual(receipt.next_epoch, 8)
        self.assertTrue(all(row.epoch == 8 for row in fresh.sigils))
        self.assertTrue(all(row.state is SigilState.INACTIVE for row in fresh.sigils))
        self.assertTrue(all(row.evidence_digest == "" for row in fresh.sigils))
        self.assertEqual(fresh.activation_plan_digest, previous.activation_plan_digest)
        require_rebirth_receipt(previous, fresh, receipt)

    def test_rebirth_is_deterministic_for_same_state_and_evidence(self) -> None:
        previous = self._contained()
        fresh_a, receipt_a = rebirth_contained_universe(previous, cause_evidence_digest="same")
        fresh_b, receipt_b = rebirth_contained_universe(previous, cause_evidence_digest="same")
        self.assertEqual(fresh_a.digest, fresh_b.digest)
        self.assertEqual(receipt_a.digest, receipt_b.digest)

    def test_receipt_tampering_is_rejected(self) -> None:
        from dataclasses import replace

        previous = self._contained()
        fresh, receipt = rebirth_contained_universe(previous, cause_evidence_digest="proof")
        tampered = replace(receipt, next_epoch=99)
        with self.assertRaises(UniverseRebirthError):
            require_rebirth_receipt(previous, fresh, tampered)


if __name__ == "__main__":
    unittest.main()
