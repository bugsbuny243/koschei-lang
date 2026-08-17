from __future__ import annotations
import hashlib
import unittest

from koschei.sentinel_defense_authority_v1 import (
    SentinelDefenseAuthorityError,
    authorize_sentinel_defense_request_v1,
    execute_sentinel_defense_request_v1,
    issue_sentinel_defense_authority_v1,
)


class SentinelDefenseAuthorityV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.project = hashlib.sha3_256(b"project").digest()
        self.target = hashlib.sha3_256(b"target").digest()
        self.reason = hashlib.sha3_256(b"reason").digest()
        self.nonce = hashlib.sha3_256(b"nonce").digest()
        self.authority = issue_sentinel_defense_authority_v1(
            project_commitment=self.project,
            epoch=7,
            actions=frozenset({"quarantine", "revoke", "canary"}),
            not_before=100,
            expires_at=200,
            max_actions=8,
            host_nonce=self.nonce,
        )

    def test_delegated_defense_action_reaches_only_host_enforcer(self) -> None:
        request = authorize_sentinel_defense_request_v1(
            self.authority,
            action="quarantine",
            target_commitment=self.target,
            reason_digest=self.reason,
            now=150,
        )
        seen = []
        self.assertTrue(execute_sentinel_defense_request_v1(request, enforcer=lambda r: seen.append(r) is None))
        self.assertEqual(seen, [request])

    def test_sentinel_cannot_widen_action_scope(self) -> None:
        with self.assertRaises(SentinelDefenseAuthorityError):
            authorize_sentinel_defense_request_v1(
                self.authority,
                action="rollback",
                target_commitment=self.target,
                reason_digest=self.reason,
                now=150,
            )

    def test_expired_or_future_authority_fails_closed(self) -> None:
        for now in (99, 200, 999):
            with self.assertRaises(SentinelDefenseAuthorityError):
                authorize_sentinel_defense_request_v1(
                    self.authority,
                    action="revoke",
                    target_commitment=self.target,
                    reason_digest=self.reason,
                    now=now,
                )

    def test_emergency_window_and_action_budget_are_bounded(self) -> None:
        with self.assertRaises(SentinelDefenseAuthorityError):
            issue_sentinel_defense_authority_v1(
                project_commitment=self.project, epoch=7,
                actions=frozenset({"quarantine"}), not_before=0,
                expires_at=3601, max_actions=1, host_nonce=self.nonce,
            )
        with self.assertRaises(SentinelDefenseAuthorityError):
            issue_sentinel_defense_authority_v1(
                project_commitment=self.project, epoch=7,
                actions=frozenset({"quarantine"}), not_before=0,
                expires_at=60, max_actions=65, host_nonce=self.nonce,
            )

    def test_repr_redacts_commitments_and_delegation(self) -> None:
        request = authorize_sentinel_defense_request_v1(
            self.authority, action="canary", target_commitment=self.target,
            reason_digest=self.reason, now=150,
        )
        text = repr(self.authority) + repr(request)
        for secretish in (self.project.hex(), self.target.hex(), self.reason.hex(), self.nonce.hex(), self.authority.delegation_digest.hex()):
            self.assertNotIn(secretish, text)

    def test_enforcer_exception_is_redacted(self) -> None:
        request = authorize_sentinel_defense_request_v1(
            self.authority, action="quarantine", target_commitment=self.target,
            reason_digest=self.reason, now=150,
        )
        def explode(_):
            raise RuntimeError("SECRET_HOST_DETAIL")
        with self.assertRaises(SentinelDefenseAuthorityError) as caught:
            execute_sentinel_defense_request_v1(request, enforcer=explode)
        self.assertEqual(str(caught.exception), "defense enforcement failed")
        self.assertNotIn("SECRET_HOST_DETAIL", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
