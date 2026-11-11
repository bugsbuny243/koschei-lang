from __future__ import annotations

import hashlib
import hmac
import unittest

from koschei.private_distribution_v1 import (
    ChannelArtifact,
    ChannelManifest,
    DownloadGrant,
    RevocationSnapshot,
    canonical_download_grant_payload,
    canonical_manifest_payload,
    canonical_revocation_payload,
    verify_private_download,
)


class PrivateDistributionV1Tests(unittest.TestCase):
    def setUp(self):
        self.key = b"k" * 32
        self.artifact = b"koschei-commercial-artifact-v1"
        self.sha = hashlib.sha256(self.artifact).hexdigest()
        self.policy = hashlib.sha256(b"policy").hexdigest()
        self.entitlement = hashlib.sha256(b"entitlement").hexdigest()
        self.row = ChannelArtifact("koschei-secure-runtime", "0.10.0", "private-stable", self.sha, self.policy, len(self.artifact))
        self.manifest = ChannelManifest(12, 100, 150, (self.row,))
        self.revocations = RevocationSnapshot(8, 105, (), (), (), ())
        self.grant = DownloadGrant("grant-001", "customer-001", self.entitlement, self.sha, "private-stable", 110, 120)

    def sign(self, payload: bytes) -> bytes:
        return hmac.new(self.key, payload, hashlib.sha256).digest()

    def verifier(self, payload: bytes, signature: bytes) -> bool:
        return hmac.compare_digest(self.sign(payload), signature)

    def kwargs(self):
        return dict(
            manifest=self.manifest,
            manifest_signature=self.sign(canonical_manifest_payload(self.manifest)),
            manifest_verifier=self.verifier,
            revocations=self.revocations,
            revocation_signature=self.sign(canonical_revocation_payload(self.revocations)),
            revocation_verifier=self.verifier,
            grant=self.grant,
            grant_signature=self.sign(canonical_download_grant_payload(self.grant)),
            grant_verifier=self.verifier,
            current_epoch=115,
            expected_channel="private-stable",
            expected_policy_hash=self.policy,
            expected_size_bytes=len(self.artifact),
            artifact_bytes=self.artifact,
            min_manifest_sequence=12,
            min_revocation_sequence=8,
        )

    def test_valid_download_is_accepted(self):
        self.assertTrue(verify_private_download(**self.kwargs()))

    def test_tampered_artifact_is_rejected(self):
        k = self.kwargs(); k["artifact_bytes"] = self.artifact + b"!"
        self.assertFalse(verify_private_download(**k))

    def test_revoked_artifact_is_rejected(self):
        rev = RevocationSnapshot(9, 110, (self.sha,), (), (), ())
        k = self.kwargs(); k["revocations"] = rev; k["revocation_signature"] = self.sign(canonical_revocation_payload(rev)); k["min_revocation_sequence"] = 9
        self.assertFalse(verify_private_download(**k))

    def test_revoked_entitlement_is_rejected_even_when_artifact_remains_valid(self):
        rev = RevocationSnapshot(9, 110, (), (self.entitlement,), (), ())
        k = self.kwargs(); k["revocations"] = rev; k["revocation_signature"] = self.sign(canonical_revocation_payload(rev)); k["min_revocation_sequence"] = 9
        self.assertFalse(verify_private_download(**k))

    def test_unrelated_entitlement_revocation_does_not_block_valid_grant(self):
        other = hashlib.sha256(b"other-entitlement").hexdigest()
        rev = RevocationSnapshot(9, 110, (), (other,), (), ())
        k = self.kwargs(); k["revocations"] = rev; k["revocation_signature"] = self.sign(canonical_revocation_payload(rev)); k["min_revocation_sequence"] = 9
        self.assertTrue(verify_private_download(**k))

    def test_malformed_revoked_entitlement_digest_fails_closed(self):
        rev = RevocationSnapshot(9, 110, (), ("not-a-digest",), (), ())
        k = self.kwargs(); k["revocations"] = rev; k["revocation_signature"] = b"signed-but-malformed"; k["min_revocation_sequence"] = 9
        self.assertFalse(verify_private_download(**k))

    def test_old_signed_manifest_replay_is_rejected(self):
        k = self.kwargs(); k["min_manifest_sequence"] = 13
        self.assertFalse(verify_private_download(**k))

    def test_old_signed_revocation_snapshot_replay_is_rejected(self):
        k = self.kwargs(); k["min_revocation_sequence"] = 9
        self.assertFalse(verify_private_download(**k))

    def test_wrong_channel_is_rejected(self):
        k = self.kwargs(); k["expected_channel"] = "private-beta"
        self.assertFalse(verify_private_download(**k))

    def test_wrong_policy_is_rejected(self):
        k = self.kwargs(); k["expected_policy_hash"] = hashlib.sha256(b"other").hexdigest()
        self.assertFalse(verify_private_download(**k))

    def test_expired_download_grant_is_rejected(self):
        k = self.kwargs(); k["current_epoch"] = 121
        self.assertFalse(verify_private_download(**k))

    def test_tampered_manifest_signature_is_rejected(self):
        k = self.kwargs(); k["manifest_signature"] = b"bad"
        self.assertFalse(verify_private_download(**k))

    def test_future_revocation_snapshot_is_rejected(self):
        rev = RevocationSnapshot(9, 116, (), (), (), ())
        k = self.kwargs(); k["revocations"] = rev; k["revocation_signature"] = self.sign(canonical_revocation_payload(rev)); k["min_revocation_sequence"] = 9
        self.assertFalse(verify_private_download(**k))


if __name__ == "__main__":
    unittest.main()
