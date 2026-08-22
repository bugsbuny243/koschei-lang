from __future__ import annotations

from dataclasses import replace
import unittest

from koschei.library_expansion_engine_v1 import compile_library_expansion
from koschei.library_proof_envelope_v1 import (
    LibraryProofError,
    make_receipt,
    require_library_proof_envelope,
    seal_library_proof_envelope,
)


class LibraryProofEnvelopeTests(unittest.TestCase):
    def _plan(self):
        return compile_library_expansion(("ka", "vor", "shi", "thal", "nur"))

    def _receipts(self, plan, *, success=True):
        return tuple(
            make_receipt(
                activation_step_id=step.activation_step_id,
                obligation=step.obligation,
                subsystem=step.subsystem,
                proof_kind=step.proof_kind,
                evidence_digest=f"evidence:{step.activation_step_id}",
                success=success,
            )
            for step in plan.steps
        )

    def test_full_universe_proofs_seal_to_allow(self) -> None:
        plan = self._plan()
        envelope = seal_library_proof_envelope(plan, self._receipts(plan))
        self.assertEqual(envelope.decision, "ALLOW")
        self.assertEqual(len(envelope.receipts), len(plan.steps))
        require_library_proof_envelope(plan, envelope)

    def test_missing_receipt_fails_closed(self) -> None:
        plan = self._plan()
        receipts = self._receipts(plan)
        with self.assertRaises(LibraryProofError):
            seal_library_proof_envelope(plan, receipts[:-1])

    def test_failed_obligation_cannot_produce_allow(self) -> None:
        plan = self._plan()
        receipts = list(self._receipts(plan))
        receipts[0] = replace(receipts[0], success=False)
        # Rebuild the receipt so the failure bit is cryptographically bound.
        receipts[0] = make_receipt(
            activation_step_id=receipts[0].activation_step_id,
            obligation=receipts[0].obligation,
            subsystem=receipts[0].subsystem,
            proof_kind=receipts[0].proof_kind,
            evidence_digest=receipts[0].evidence_digest,
            success=False,
        )
        envelope = seal_library_proof_envelope(plan, receipts)
        self.assertEqual(envelope.decision, "DENY")

    def test_receipt_cannot_be_rebound_to_another_obligation(self) -> None:
        plan = self._plan()
        receipts = list(self._receipts(plan))
        receipts[0] = replace(receipts[0], obligation="derive-least-authority")
        with self.assertRaises(LibraryProofError):
            seal_library_proof_envelope(plan, receipts)

    def test_envelope_is_deterministic(self) -> None:
        plan = self._plan()
        a = seal_library_proof_envelope(plan, self._receipts(plan))
        b = seal_library_proof_envelope(plan, reversed(self._receipts(plan)))
        self.assertEqual(a.digest, b.digest)

    def test_tampered_envelope_digest_is_rejected(self) -> None:
        plan = self._plan()
        envelope = seal_library_proof_envelope(plan, self._receipts(plan))
        with self.assertRaises(LibraryProofError):
            require_library_proof_envelope(plan, replace(envelope, digest="00" * 32))


if __name__ == "__main__":
    unittest.main()
