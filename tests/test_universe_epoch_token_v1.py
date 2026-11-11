from __future__ import annotations

import unittest

from koschei.universe_epoch_token_v1 import (
    UniverseEpochTokenError,
    mint_sigil_epoch_token,
    require_current_sigil_token,
)
from koschei.universe_rebirth_v1 import rebirth_contained_universe
from koschei.universe_state_machine_v1 import (
    SigilState,
    contain_universe,
    initial_universe_state,
    transition_sigil,
)


def _activate(state, sigil: str):
    state = transition_sigil(state, sigil, SigilState.PREPARED, evidence_digest=f"{sigil}-prepare")
    state = transition_sigil(state, sigil, SigilState.SEALED, evidence_digest=f"{sigil}-seal")
    state = transition_sigil(state, sigil, SigilState.ACTIVE, evidence_digest=f"{sigil}-active")
    return state


class UniverseEpochTokenTests(unittest.TestCase):
    def test_active_sigil_can_mint_and_validate_token(self) -> None:
        state = initial_universe_state(("ka", "vor"), epoch=3)
        state = _activate(state, "ka")
        state = _activate(state, "vor")
        token = mint_sigil_epoch_token(state, "vor")
        require_current_sigil_token(state, token, expected_sigil="vor")
        self.assertEqual(token.epoch, 3)

    def test_inactive_sigil_cannot_mint_token(self) -> None:
        state = initial_universe_state(("ka",), epoch=1)
        with self.assertRaises(UniverseEpochTokenError):
            mint_sigil_epoch_token(state, "ka")

    def test_state_change_invalidates_snapshot_token(self) -> None:
        state = initial_universe_state(("ka", "vor"), epoch=2)
        state = _activate(state, "ka")
        token = mint_sigil_epoch_token(state, "ka")
        state = transition_sigil(state, "vor", SigilState.PREPARED, evidence_digest="vor-prepare")
        with self.assertRaises(UniverseEpochTokenError):
            require_current_sigil_token(state, token)

    def test_rebirth_rejects_old_epoch_token(self) -> None:
        state = initial_universe_state(("ka", "vor"), epoch=7)
        state = _activate(state, "ka")
        state = _activate(state, "vor")
        old = mint_sigil_epoch_token(state, "vor")
        contained = contain_universe(state, evidence_digest="contain-7")
        fresh, _receipt = rebirth_contained_universe(
            contained, cause_evidence_digest="recovery-proof-7"
        )
        with self.assertRaises(UniverseEpochTokenError):
            require_current_sigil_token(fresh, old)

    def test_tampered_token_digest_is_rejected(self) -> None:
        state = initial_universe_state(("ka",), epoch=4)
        state = _activate(state, "ka")
        token = mint_sigil_epoch_token(state, "ka")
        tampered = type(token)(
            sigil=token.sigil,
            epoch=token.epoch,
            activation_plan_digest=token.activation_plan_digest,
            lifecycle_evidence_digest=token.lifecycle_evidence_digest,
            state_digest=token.state_digest,
            token_digest="00" * 32,
        )
        with self.assertRaises(UniverseEpochTokenError):
            require_current_sigil_token(state, tampered)


if __name__ == "__main__":
    unittest.main()
