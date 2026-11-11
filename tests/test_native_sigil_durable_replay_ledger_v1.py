from pathlib import Path
import tempfile
import unittest

from koschei.native_sigil_durable_replay_ledger_v1 import DurableReplayLedger
from koschei.native_sigil_enforcement_gate_v1 import EnforcementDecision
from koschei.native_sigil_replay_ledger_v1 import NativeSigilReplayError


class _Request:
    digest = "req-digest"
    effect_id = "effect-1"
    epoch = 7


class DurableReplayLedgerTests(unittest.TestCase):
    def _decision(self, digest: str = "decision-1") -> EnforcementDecision:
        return EnforcementDecision(
            decision="ALLOW",
            effect_id="effect-1",
            native_mir_fingerprint="mir",
            proof_digest="proof-1",
            failed_obligations=(),
            digest=digest,
        )

    def test_claim_survives_restart_and_cannot_be_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "replay.sqlite3"
            ledger = DurableReplayLedger(path)
            first = ledger.claim(_Request(), "proof-1")
            self.assertEqual(first.state, "CLAIMED")
            ledger.close()

            ledger = DurableReplayLedger(path)
            restored = ledger.get(_Request.digest)
            self.assertIsNotNone(restored)
            self.assertEqual(restored.state, "CLAIMED")
            with self.assertRaises(NativeSigilReplayError):
                ledger.claim(_Request(), "proof-1")
            ledger.close()

    def test_terminal_state_survives_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "replay.sqlite3"
            ledger = DurableReplayLedger(path)
            ledger.claim(_Request(), "proof-1")
            decision = self._decision()
            # The durable ledger only needs the decision digest for finality sealing.
            object.__setattr__(decision, "digest", "decision-1")
            final = ledger.finalize(
                _Request(), "proof-1", decision, state="COMMITTED"
            )
            self.assertEqual(final.state, "COMMITTED")
            ledger.close()

            ledger = DurableReplayLedger(path)
            restored = ledger.get(_Request.digest)
            self.assertEqual(restored.state, "COMMITTED")
            with self.assertRaises(NativeSigilReplayError):
                ledger.claim(_Request(), "proof-1")
            ledger.close()

    def test_unresolved_claims_are_fail_closed_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "replay.sqlite3"
            ledger = DurableReplayLedger(path)
            ledger.claim(_Request(), "proof-1")
            ledger.close()

            ledger = DurableReplayLedger(path)
            unresolved = ledger.unresolved_claims()
            self.assertEqual(len(unresolved), 1)
            self.assertEqual(unresolved[0].state, "CLAIMED")
            ledger.close()


if __name__ == "__main__":
    unittest.main()
