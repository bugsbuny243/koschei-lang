from __future__ import annotations

from dataclasses import replace
import hashlib
import unittest

from koschei.reality_evidence_ledger_v1 import (
    RealityEvidenceError,
    RealityEvidenceLedgerV1,
    append_reality_evidence_v1,
    project_commitment_v1,
    sentinel_evidence_view_v1,
    verify_reality_evidence_ledger_v1,
)


class RealityEvidenceLedgerV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.project_id = bytes.fromhex("11" * 16)
        self.authority = hashlib.sha3_256(b"authority:run:object-22").digest()
        self.artifact = hashlib.sha3_256(b"artifact:sealed-native-ir").digest()
        self.policy = hashlib.sha3_256(b"policy:least-authority-v1").digest()

    def _append(self, ledger: RealityEvidenceLedgerV1, *, command="run", outcome="ALLOW"):
        return append_reality_evidence_v1(
            ledger,
            project_id=self.project_id,
            epoch=7,
            command=command,
            authority_scope_digest=self.authority,
            artifact_digest=self.artifact,
            policy_digest=self.policy,
            outcome=outcome,
        )

    def test_append_creates_verified_hash_chain(self) -> None:
        ledger = self._append(RealityEvidenceLedgerV1(), command="check")
        ledger = self._append(ledger, command="run")
        verify_reality_evidence_ledger_v1(ledger)
        self.assertEqual([record.sequence for record in ledger.records], [1, 2])
        self.assertEqual(ledger.records[1].previous_digest, ledger.records[0].record_digest)
        self.assertNotEqual(ledger.records[0].record_digest, ledger.records[1].record_digest)

    def test_mutating_any_bound_fact_breaks_verification(self) -> None:
        ledger = self._append(RealityEvidenceLedgerV1())
        original = ledger.records[0]
        mutations = (
            replace(original, epoch=8),
            replace(original, outcome="DENY"),
            replace(original, artifact_digest=hashlib.sha3_256(b"forged").digest()),
            replace(original, policy_digest=hashlib.sha3_256(b"widened-policy").digest()),
        )
        for forged in mutations:
            with self.subTest(forged=forged.outcome):
                with self.assertRaises(RealityEvidenceError):
                    verify_reality_evidence_ledger_v1(RealityEvidenceLedgerV1((forged,)))

    def test_reordering_or_splicing_records_is_detected(self) -> None:
        first = self._append(RealityEvidenceLedgerV1(), command="check")
        second = self._append(first, command="run")
        with self.assertRaises(RealityEvidenceError):
            verify_reality_evidence_ledger_v1(
                RealityEvidenceLedgerV1((second.records[1], second.records[0]))
            )
        with self.assertRaises(RealityEvidenceError):
            verify_reality_evidence_ledger_v1(
                RealityEvidenceLedgerV1((second.records[1],))
            )

    def test_observer_view_is_read_only_and_secret_redacted(self) -> None:
        ledger = self._append(RealityEvidenceLedgerV1())
        view = sentinel_evidence_view_v1(ledger)
        self.assertEqual(len(view), 1)
        self.assertEqual(view[0].command, "run")
        self.assertEqual(view[0].outcome, "ALLOW")
        self.assertEqual(view[0].project_commitment, project_commitment_v1(self.project_id))
        rendered = repr(ledger.records[0]) + repr(view[0])
        self.assertNotIn(self.project_id.hex(), rendered)
        self.assertNotIn(self.authority.hex(), repr(ledger.records[0]))
        self.assertFalse(hasattr(view[0], "authority_scope_digest"))
        self.assertFalse(hasattr(view[0], "artifact_digest"))
        self.assertFalse(hasattr(view[0], "policy_digest"))

    def test_evidence_cannot_mint_or_carry_execution_authority(self) -> None:
        ledger = self._append(RealityEvidenceLedgerV1())
        record = ledger.records[0]
        self.assertFalse(hasattr(record, "provider"))
        self.assertFalse(hasattr(record, "temporal_key"))
        self.assertFalse(hasattr(record, "temporal_handle"))
        self.assertFalse(hasattr(record, "execute"))

    def test_noncanonical_inputs_fail_closed(self) -> None:
        with self.assertRaises(RealityEvidenceError):
            append_reality_evidence_v1(
                RealityEvidenceLedgerV1(),
                project_id=b"short",
                epoch=1,
                command="run",
                authority_scope_digest=self.authority,
                artifact_digest=self.artifact,
                policy_digest=self.policy,
                outcome="ALLOW",
            )
        with self.assertRaises(RealityEvidenceError):
            append_reality_evidence_v1(
                RealityEvidenceLedgerV1(),
                project_id=self.project_id,
                epoch=0,
                command="run",
                authority_scope_digest=self.authority,
                artifact_digest=self.artifact,
                policy_digest=self.policy,
                outcome="ALLOW",
            )


if __name__ == "__main__":
    unittest.main()
