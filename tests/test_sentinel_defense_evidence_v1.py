from __future__ import annotations

import hashlib
import unittest

from koschei.reality_evidence_ledger_v1 import (
    RealityEvidenceLedgerV1,
    project_commitment_v1,
    verify_reality_evidence_ledger_v1,
)
from koschei.sentinel_defense_authority_v1 import (
    authorize_sentinel_defense_request_v1,
    issue_sentinel_defense_authority_v1,
)
from koschei.sentinel_defense_evidence_v1 import (
    SentinelDefenseEvidenceError,
    execute_sentinel_defense_with_evidence_v1,
)


class SentinelDefenseEvidenceV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.project_id = bytes.fromhex("11" * 16)
        self.project_commitment = project_commitment_v1(self.project_id)
        self.authority = issue_sentinel_defense_authority_v1(
            project_commitment=self.project_commitment,
            epoch=7,
            actions=frozenset({"quarantine", "revoke", "canary"}),
            not_before=100,
            expires_at=200,
            max_actions=8,
            host_nonce=hashlib.sha3_256(b"host").digest(),
        )

    def _request(self, action: str = "quarantine"):
        return authorize_sentinel_defense_request_v1(
            self.authority,
            action=action,  # type: ignore[arg-type]
            target_commitment=hashlib.sha3_256(b"target").digest(),
            reason_digest=hashlib.sha3_256(b"reason").digest(),
            now=150,
        )

    def test_allow_is_chained_as_quarantine_evidence(self) -> None:
        result = execute_sentinel_defense_with_evidence_v1(
            self._request(),
            project_id=self.project_id,
            ledger=RealityEvidenceLedgerV1(),
            enforcer=lambda request: True,
        )
        self.assertTrue(result.enforced)
        self.assertEqual(result.outcome, "ALLOW")
        self.assertEqual(result.ledger.records[-1].command, "quarantine")
        verify_reality_evidence_ledger_v1(result.ledger)

    def test_denied_revoke_is_still_evidence(self) -> None:
        result = execute_sentinel_defense_with_evidence_v1(
            self._request("revoke"),
            project_id=self.project_id,
            ledger=RealityEvidenceLedgerV1(),
            enforcer=lambda request: False,
        )
        self.assertFalse(result.enforced)
        self.assertEqual(result.outcome, "DENY")
        self.assertEqual(result.ledger.records[-1].command, "revoke")
        verify_reality_evidence_ledger_v1(result.ledger)

    def test_host_failure_returns_redacted_fail_evidence(self) -> None:
        secret = "HOST_INTERNAL_SECRET"
        def fail(_request):
            raise RuntimeError(secret)

        result = execute_sentinel_defense_with_evidence_v1(
            self._request(),
            project_id=self.project_id,
            ledger=RealityEvidenceLedgerV1(),
            enforcer=fail,
        )
        self.assertEqual(result.outcome, "FAIL")
        self.assertNotIn(secret, repr(result))
        self.assertEqual(result.ledger.records[-1].outcome, "FAIL")
        verify_reality_evidence_ledger_v1(result.ledger)

    def test_project_splice_is_rejected_before_enforcement(self) -> None:
        touched = []
        with self.assertRaises(SentinelDefenseEvidenceError):
            execute_sentinel_defense_with_evidence_v1(
                self._request(),
                project_id=bytes.fromhex("22" * 16),
                ledger=RealityEvidenceLedgerV1(),
                enforcer=lambda request: touched.append(request) or True,
            )
        self.assertEqual(touched, [])

    def test_canary_maps_to_observation_until_ledger_schema_expands(self) -> None:
        result = execute_sentinel_defense_with_evidence_v1(
            self._request("canary"),
            project_id=self.project_id,
            ledger=RealityEvidenceLedgerV1(),
            enforcer=lambda request: True,
        )
        self.assertEqual(result.ledger.records[-1].command, "observe")
        verify_reality_evidence_ledger_v1(result.ledger)


if __name__ == "__main__":
    unittest.main()
