from __future__ import annotations

import unittest

from koschei.universe_state_machine_v1 import (
    SigilState,
    UniverseStateError,
    contain_universe,
    initial_universe_state,
    require_fully_active,
    transition_sigil,
)


class UniverseStateMachineTests(unittest.TestCase):
    def test_sigil_cannot_skip_prepare_and_seal(self) -> None:
        state = initial_universe_state(("ka", "vor"))
        with self.assertRaises(UniverseStateError):
            transition_sigil(state, "ka", SigilState.ACTIVE, evidence_digest="e1")

    def test_ka_must_activate_before_other_sigils(self) -> None:
        state = initial_universe_state(("ka", "vor"))
        state = transition_sigil(state, "vor", SigilState.PREPARED, evidence_digest="v1")
        state = transition_sigil(state, "vor", SigilState.SEALED, evidence_digest="v2")
        with self.assertRaises(UniverseStateError):
            transition_sigil(state, "vor", SigilState.ACTIVE, evidence_digest="v3")

    def test_full_activation_is_explicit(self) -> None:
        state = initial_universe_state(("ka", "vor"))
        for target, evidence in (
            (SigilState.PREPARED, "k1"),
            (SigilState.SEALED, "k2"),
            (SigilState.ACTIVE, "k3"),
        ):
            state = transition_sigil(state, "ka", target, evidence_digest=evidence)
        for target, evidence in (
            (SigilState.PREPARED, "v1"),
            (SigilState.SEALED, "v2"),
            (SigilState.ACTIVE, "v3"),
        ):
            state = transition_sigil(state, "vor", target, evidence_digest=evidence)
        require_fully_active(state)

    def test_containment_is_terminal(self) -> None:
        state = contain_universe(initial_universe_state(("ka", "vor")), evidence_digest="incident")
        self.assertTrue(all(row.state is SigilState.CONTAINED for row in state.sigils))
        with self.assertRaises(UniverseStateError):
            transition_sigil(state, "ka", SigilState.PREPARED, evidence_digest="restart")

    def test_state_digest_is_deterministic(self) -> None:
        left = initial_universe_state(("ka", "vor", "nur"))
        right = initial_universe_state(("ka", "vor", "nur"))
        self.assertEqual(left.digest, right.digest)


if __name__ == "__main__":
    unittest.main()
