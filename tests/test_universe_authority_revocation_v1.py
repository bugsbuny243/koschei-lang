from pathlib import Path
import tempfile
import unittest

from koschei.universe_authority_revocation_v1 import (
    AuthorityRevocationError,
    DurableAuthorityRevocationRegistry,
)
from koschei.universe_epoch_token_v1 import mint_sigil_epoch_token
from koschei.universe_nuclear_containment_v1 import enter_nuclear_containment
from koschei.universe_state_machine_v1 import (
    SigilState,
    initial_universe_state,
    transition_sigil,
)


def _active_state():
    state = initial_universe_state(("ka", "vor"), epoch=7)
    for sigil in ("ka", "vor"):
        state = transition_sigil(state, sigil, SigilState.PREPARED, evidence_digest=f"{sigil}-prepared")
        state = transition_sigil(state, sigil, SigilState.SEALED, evidence_digest=f"{sigil}-sealed")
        state = transition_sigil(state, sigil, SigilState.ACTIVE, evidence_digest=f"{sigil}-active")
    return state


class AuthorityRevocationTests(unittest.TestCase):
    def test_individual_token_revocation_is_durable(self) -> None:
        state = _active_state()
        token = mint_sigil_epoch_token(state, "vor")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "revocations.sqlite3"
            registry = DurableAuthorityRevocationRegistry(path)
            self.assertFalse(registry.is_revoked(token))
            registry.revoke_token(token, cause_digest="manual-revoke")
            self.assertTrue(registry.is_revoked(token))
            registry.close()

            registry = DurableAuthorityRevocationRegistry(path)
            self.assertTrue(registry.is_revoked(token))
            with self.assertRaises(AuthorityRevocationError):
                registry.require_live(token)
            registry.close()

    def test_nuclear_containment_revokes_every_token_in_epoch(self) -> None:
        previous = _active_state()
        ka_token = mint_sigil_epoch_token(previous, "ka")
        vor_token = mint_sigil_epoch_token(previous, "vor")
        contained, receipt = enter_nuclear_containment(
            previous, cause_evidence_digest="catastrophic-evidence"
        )

        with tempfile.TemporaryDirectory() as directory:
            registry = DurableAuthorityRevocationRegistry(Path(directory) / "revocations.sqlite3")
            record = registry.apply_nuclear_revocation(previous, contained, receipt)
            self.assertEqual(record.scope, "EPOCH")
            self.assertEqual(record.epoch, 7)
            self.assertTrue(registry.is_revoked(ka_token))
            self.assertTrue(registry.is_revoked(vor_token))
            registry.close()

    def test_new_epoch_token_is_not_killed_by_old_epoch_tombstone(self) -> None:
        old = _active_state()
        old_token = mint_sigil_epoch_token(old, "vor")
        contained, receipt = enter_nuclear_containment(
            old, cause_evidence_digest="catastrophic-evidence"
        )
        # A separate freshly activated epoch with the same canonical plan.
        fresh = initial_universe_state(("ka", "vor"), epoch=8)
        for sigil in ("ka", "vor"):
            fresh = transition_sigil(fresh, sigil, SigilState.PREPARED, evidence_digest=f"{sigil}-prepared-8")
            fresh = transition_sigil(fresh, sigil, SigilState.SEALED, evidence_digest=f"{sigil}-sealed-8")
            fresh = transition_sigil(fresh, sigil, SigilState.ACTIVE, evidence_digest=f"{sigil}-active-8")
        new_token = mint_sigil_epoch_token(fresh, "vor")

        with tempfile.TemporaryDirectory() as directory:
            registry = DurableAuthorityRevocationRegistry(Path(directory) / "revocations.sqlite3")
            registry.apply_nuclear_revocation(old, contained, receipt)
            self.assertTrue(registry.is_revoked(old_token))
            self.assertFalse(registry.is_revoked(new_token))
            registry.require_live(new_token)
            registry.close()


if __name__ == "__main__":
    unittest.main()
